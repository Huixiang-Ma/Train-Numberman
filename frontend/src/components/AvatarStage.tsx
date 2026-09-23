import { useEffect, useRef, type MutableRefObject } from 'react'
import * as THREE from 'three'
import type { AvatarAssets } from '../hooks/useAvatarAssets'

export interface AvatarVisualState {
  emotion: string
  motion: string
  speaking: boolean
  mouth: number
}

/**
 * 骨骼槽位（顺序即着色器中的应用顺序；腕手骨必须在臂骨之后才能吃到形变）。
 */
const BONE_COUNT = 9
const HEAD = 0
const BROW = 1
const FACE = 2
const BODY = 3
const ARM_L = 4
const HAND_L = 5
const ARM_R = 6
const HAND_R = 7
/** 下颌：张口时下巴下沉。旋转做不到这件事（下巴只能绕枢轴自转），必须用位移 */
const JAW = 8

/** 视位 → 口型形状 [宽比, 高比]，让开口不只是"张大"，而是有圆唇/扁唇之分 */
const VISEME_SHAPE: Record<string, [number, number]> = {
  sil: [0.92, 0.5],
  M: [0.94, 0.45],
  F: [0.96, 0.62],
  C: [1.02, 0.62],
  A: [1.0, 1.15],
  O: [0.7, 1.25],
  E: [1.12, 0.82],
  I: [1.16, 0.68],
  U: [0.72, 0.95],
}

interface Props {
  state: AvatarVisualState
  assets: AvatarAssets
  /** 口型开合度，由音频播放时钟逐帧写入 */
  mouthRef?: MutableRefObject<number>
  /** 当前视位（决定口型形状） */
  visemeRef?: MutableRefObject<string | null>
}

// ==========================================================================
// 动作基础件
// ==========================================================================

const clamp = (value: number, min = 0, max = 1) => Math.min(max, Math.max(min, value))
const easeOutCubic = (p: number) => 1 - Math.pow(1 - p, 3)
const easeInQuad = (p: number) => p * p
const easeOutQuad = (p: number) => 1 - (1 - p) * (1 - p)
const easeInOutQuad = (p: number) => (p < 0.5 ? 2 * p * p : 1 - Math.pow(-2 * p + 2, 2) / 2)
/** 把正弦削出更清晰的节拍：过零更平、峰值更尖，避免"平滑晃动"的敷衍感 */
const shapeBeat = (value: number) => Math.sign(value) * Math.pow(Math.abs(value), 0.62)

/**
 * 预备动作（迪士尼动画十二法则之 anticipation）。
 * 人做任何有意图的动作前，都会先向反方向做一个很小的准备位移；
 * 直接从静止进入动作会显得"被推动"，这是"僵硬感"的常见来源。
 * 返回值是 0→1→0 的平滑凸起，用它反向施加一个微小的先行位移。
 */
const anticipation = (t: number, duration: number) =>
  t < 0 || t >= duration ? 0 : Math.sin(Math.PI * clamp(t / duration))

/**
 * 1/f（粉红）噪声表。
 *
 * 自然人体（含静立时的微动）的功率谱是 1/f^β，而"少数几个正弦叠加"在频谱上
 * 只留几根孤立尖峰——不论怎么调频率与幅度，都摆脱不了机械感。这是"动作僵硬"
 * 在信号层面的根因，参照 Talking Head Anime 3 与 SadTalker 类工作的做法：
 * 用具备自然频谱的驱动信号，而不是手写正弦。
 *
 * 做法：频域合成（幅度 ∝ 1/sqrt(f)、相位随机）后归一化。表长 2048 覆盖 140s，
 * 足以承载待机层 ≤1Hz 的全部分量，且循环周期远长于一次会话的观感阈值。
 */
const PINK_SECONDS = 140
const PINK_SIZE = 2048

function buildPinkNoise(size = PINK_SIZE): Float32Array {
  const out = new Float32Array(size)
  const half = size >> 1
  for (let k = 1; k < half; k += 1) {
    const amplitude = 1 / Math.sqrt(k)
    const phase = Math.random() * Math.PI * 2
    const step = (2 * Math.PI * k) / size
    for (let i = 0; i < size; i += 1) out[i] += amplitude * Math.sin(step * i + phase)
  }
  let peak = 1e-6
  for (let i = 0; i < size; i += 1) peak = Math.max(peak, Math.abs(out[i]))
  for (let i = 0; i < size; i += 1) out[i] /= peak
  return out
}

const pink = buildPinkNoise()

/** 按「时间 × 速度 + 偏移」在噪声表上取值；各通道用不同偏移，互不相关 */
function pinkAt(offset: number, seconds: number, speed = 1): number {

  const wrapped = (((offset + seconds * speed) % PINK_SECONDS) + PINK_SECONDS) % PINK_SECONDS
  const position = (wrapped / PINK_SECONDS) * PINK_SIZE
  const index = Math.floor(position) % PINK_SIZE
  const next = (index + 1) % PINK_SIZE
  const fraction = position - Math.floor(position)
  return pink[index] * (1 - fraction) + pink[next] * fraction
}

/**
 * 临界阻尼弹簧：动作不再逐帧硬跳，而是带速度与余振地趋近目标。
 * 各通道刚度不同 → 天然产生"快的先动、重的后动"的层次。
 */
class Spring {
  value = 0
  velocity = 0
  target = 0
  constructor(public stiffness: number, public underdamp = 0.42) {}

  step(delta: number) {
    const substeps = Math.min(10, Math.max(1, Math.ceil(delta / 0.008)))
    const h = delta / substeps
    const damping = (2 - this.underdamp) * Math.sqrt(this.stiffness)
    for (let index = 0; index < substeps; index += 1) {
      const accel = this.stiffness * (this.target - this.value) - damping * this.velocity
      this.velocity += accel * h
      this.value += this.velocity * h
    }
    return this.value
  }
}

/** 目标值延迟线：下游关节读取上游若干毫秒前的目标，形成跟随与鞭梢 */
class DelayLine {
  private samples: { t: number; v: number }[] = []

  push(t: number, v: number) {
    this.samples.push({ t, v })
    if (this.samples.length > 300) this.samples.shift()
  }

  read(t: number, lag: number) {
    const wanted = t - lag
    for (let index = this.samples.length - 1; index >= 0; index -= 1) {
      if (this.samples[index].t <= wanted) return this.samples[index].v
    }
    return this.samples.length ? this.samples[0].v : 0
  }
}

/**
 * 情绪 → 面部表情参数。
 *
 * 取值刻意压得很小：照片级 2D 形变有严格的可信预算，
 * 眉毛是"长在皮肤上"的，独立大位移会拉扯周围皮肤，必然违和（恐怖谷）。
 * 因此表情主要靠「眼睑眯合 + 头部姿态 + 动作节奏」表达，
 * 眉骨与下脸只做 1~2px 量级的微动，作为生命感点缀而非主要手段。
 */
interface Expression {
  browRaise: number
  browTilt: number
  faceLift: number
  squint: number
  energy: number
}

const EMOTIONS: Record<string, Expression> = {
  calm: { browRaise: 0.012, browTilt: 0, faceLift: 0.24, squint: 0.04, energy: 0.95 },
  cheerful: { browRaise: 0.037, browTilt: 0.02, faceLift: 0.85, squint: 0.32, energy: 1.2 },
  curious: { browRaise: 0.048, browTilt: 0.031, faceLift: 0.3, squint: 0.06, energy: 1.1 },
  gentle: { browRaise: 0.02, browTilt: -0.013, faceLift: 0.45, squint: 0.12, energy: 0.8 },
}

type Channel =
  | 'headYaw'
  | 'headPitch'
  | 'headTilt'
  | 'headBob'
  | 'browRaise'
  | 'browTilt'
  | 'faceLift'
  | 'armL'
  | 'handL'
  | 'armR'
  | 'handR'

interface Impulse {
  channel: Channel
  amount: number
  start: number
  duration: number
}

/**
 * 工单18 · 数字人 2.5D 驱动舞台
 *
 * 呈现约定：背景透明、画面中只有人物本体；允许细微的整体身体起伏。
 *
 * 让动作"不僵硬"的六条设计：
 *   1) 2.5D 转头与俯仰：头骨带缩放，yaw 收窄+横移、pitch 压扁+纵移，
 *      解决 2D 人像只能"平面晃"的纸板感；
 *   2) 振幅到位：所有通道按画布像素反推幅度，避免出现亚像素级"看不见的动作"；
 *   3) 弹簧阻尼 + 通道刚度差：快的先动、重的后动，自带缓入缓出与余振；
 *   4) 关节链延迟跟随：腕手读取臂骨延迟目标并放大，形成鞭梢；
 *   5) 微动作脉冲：随机调度小幅转头/挑眉/重心移动，消除周期性"摆拍"；
 *   6) 语音耦合：口腔开合驱动头部重音与手势，身体与声音同源。
 */
export default function AvatarStage({ state, assets, mouthRef, visemeRef }: Props) {
  const mountRef = useRef<HTMLDivElement>(null)
  const stateRef = useRef(state)
  stateRef.current = state
  const assetsRef = useRef(assets)
  assetsRef.current = assets
  const mouthLiveRef = useRef(mouthRef)
  mouthLiveRef.current = mouthRef
  const visemeLiveRef = useRef(visemeRef)
  visemeLiveRef.current = visemeRef

  useEffect(() => {
    const mount = mountRef.current
    if (!mount) return

    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const scene = new THREE.Scene()
    const camera = new THREE.PerspectiveCamera(40, 1, 0.1, 100)
    camera.position.set(0, 0, 6)

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    renderer.setClearColor(0x000000, 0)
    mount.appendChild(renderer.domElement)
    renderer.domElement.style.width = '100%'
    renderer.domElement.style.height = '100%'
    renderer.domElement.style.display = 'block'

    const root = new THREE.Group()
    scene.add(root)

    const boneCenter = Array.from({ length: BONE_COUNT }, () => new THREE.Vector4(0, 0, 0, 0))
    const boneAxis = Array.from({ length: BONE_COUNT }, () => new THREE.Vector4(0, 1, 1, 1))
    const bonePivot = Array.from({ length: BONE_COUNT }, () => new THREE.Vector4(0, 0, 0, 0))
    const boneShift = Array.from({ length: BONE_COUNT }, () => new THREE.Vector4(0, 0, 0, 0))
    const boneScale = Array.from({ length: BONE_COUNT }, () => new THREE.Vector4(1, 1, 0, 0))

    let planeWidth = 2.8
    let planeHeight = 4.2
    const neckPlane = new THREE.Vector2(0, 0)
    // 叠加层自身缩放（口型开合），与头骨缩放相乘后写入
    const mouthOwnScale = new THREE.Vector2(1, 1)
    // 口型叠加层的基准高度（平面单位），下颌下沉量由它推出，两者结构绑定
    let mouthBaseHeight = 0.12
    // 眨眼混合权重（0=睁眼，1=闭眼），由动画循环逐帧写入
    const blinkUniform = { value: 0 }
    // 衣物微风：累计时间与强度，均由动画循环逐帧写入（强度 0 = 关闭）
    const windTimeUniform = { value: 0 }
    const windStrengthUniform = { value: 0 }
    const overlays: { object: THREE.Mesh; u: number; v: number; baseScaleX: () => number; baseScaleY: () => number }[] = []

    // 各通道弹簧。刚度必须能跟上音节周期（约 0.19s）：
    // 之前把刚度压得过低（眉部 k=70，整定时间约 0.5s），面部根本跟不上语音，
    // 于是被"平均"成一个凝固的姿态——这才是"整体不协调"的真正原因。
    // 放慢该放慢的（姿态层），跟得上该跟上的（音节层）。
    const springs: Record<Channel, Spring> = {
      headYaw: new Spring(40),
      headPitch: new Spring(62),
      headTilt: new Spring(46),
      headBob: new Spring(140),
      browRaise: new Spring(108, 0.5),
      browTilt: new Spring(86, 0.45),
      faceLift: new Spring(75),
      armL: new Spring(78),
      handL: new Spring(145, 0.5),
      armR: new Spring(78),
      handR: new Spring(145, 0.5),
    }
    const mouthSpring = new Spring(105, 0.25)
    // 视位形状（宽高比）同样要过弹簧：直接按视位切换会在切换瞬间硬跳
    const mouthWidthSpring = new Spring(110, 0.35)
    const mouthHeightSpring = new Spring(110, 0.35)
    // 语音信号的三个时间尺度，全部源自同一路信号：
    //   fast   = 口腔开合本身（音节级，≈0.19s）
    //   medium = 短语内的起伏（≈0.3s）
    //   slow   = 姿态基准（≈0.9s）
    // 同步由"同源"保证，层次由"不同时间常数"保证——两者不矛盾。
    const mediumEnvSpring = new Spring(60)
    const slowEnvSpring = new Spring(14)
    const armDelay = new DelayLine()
    const browDelay = new DelayLine()

    const impulses: Impulse[] = []
    const addImpulse = (channel: Channel, amount: number, duration: number, at: number) => {
      impulses.push({ channel, amount, start: at, duration })
      if (impulses.length > 24) impulses.shift()
    }

    const meta = assetsRef.current.meta
    const source = assetsRef.current.texture
    let mouthMesh: THREE.Mesh | null = null

    if (assetsRef.current.status === 'ready' && source && meta) {
      const aspect = meta.width / meta.height
      const visibleHeight = 2 * camera.position.z * Math.tan((camera.fov * Math.PI) / 360)
      planeHeight = visibleHeight * 0.99
      planeWidth = planeHeight * aspect

      const toX = (u: number) => (u - 0.5) * planeWidth
      const toY = (v: number) => (0.5 - v) * planeHeight

      const texture = new THREE.CanvasTexture(source)
      texture.colorSpace = THREE.SRGBColorSpace
      texture.anisotropy = 4

      // 闭眼素材：RGB 为闭眼画面，alpha 为「眨眼影响区域」的羽化蒙版。
      // 用交叉淡入替代"贴皮肤补丁"或"纵向压扁"——前者必然带色差与接缝，
      // 后者会把睁大的虹膜压成一条横缝，两者都藏不住眼球。
      // 素材缺失时退回原图：mix(原图, 原图) 等于不变，不影响其余动作。
      const blinkSource = assetsRef.current.blink ?? source
      const blinkTexture = new THREE.CanvasTexture(blinkSource)
      blinkTexture.colorSpace = THREE.SRGBColorSpace
      blinkTexture.anisotropy = 4

      // 衣物微风遮罩：派生灰度图。缺失时退回 1×1 空白画布 —— 采样恒为 0，
      // 等价于关闭风感，不会让衣物撕裂或整幅画面位移。
      const clothSource = assetsRef.current.clothMask
      const clothTexture = new THREE.CanvasTexture(clothSource ?? document.createElement('canvas'))
      // 遮罩是权重数据而非颜色，不做 sRGB 转换，避免中间调被非线性压缩
      clothTexture.colorSpace = THREE.NoColorSpace
      clothTexture.anisotropy = 4

      const material = new THREE.MeshBasicMaterial({ map: texture, transparent: true, depthWrite: false })
      material.onBeforeCompile = (shader) => {
        shader.uniforms.uBoneCenter = { value: boneCenter }
        shader.uniforms.uBoneAxis = { value: boneAxis }
        shader.uniforms.uBonePivot = { value: bonePivot }
        shader.uniforms.uBoneShift = { value: boneShift }
        shader.uniforms.uBoneScale = { value: boneScale }
        shader.uniforms.uBlinkMap = { value: blinkTexture }
        shader.uniforms.uBlink = blinkUniform
        shader.uniforms.uClothMask = { value: clothTexture }
        shader.uniforms.uWindTime = windTimeUniform
        shader.uniforms.uWindStrength = windStrengthUniform
        shader.fragmentShader = `
uniform sampler2D uBlinkMap;
uniform float uBlink;
${shader.fragmentShader}`
        // 只在闭眼素材 alpha 覆盖的眼部区域参与混合，嘴部与身体完全不受影响
        shader.fragmentShader = shader.fragmentShader.replace(
          '#include <map_fragment>',
          `
#ifdef USE_MAP
  vec4 openSample = texture2D( map, vMapUv );
  vec4 blinkSample = texture2D( uBlinkMap, vMapUv );
  float blinkMix = clamp( uBlink, 0.0, 1.0 ) * blinkSample.a;
  diffuseColor *= vec4( mix( openSample.rgb, blinkSample.rgb, blinkMix ), openSample.a );
#endif
`,
        )
        shader.vertexShader = `
uniform vec4 uBoneCenter[ ${BONE_COUNT} ];
uniform vec4 uBoneAxis[ ${BONE_COUNT} ];
uniform vec4 uBonePivot[ ${BONE_COUNT} ];
uniform vec4 uBoneShift[ ${BONE_COUNT} ];
uniform vec4 uBoneScale[ ${BONE_COUNT} ];
uniform sampler2D uClothMask;
uniform float uWindTime;
uniform float uWindStrength;
${shader.vertexShader}`
        shader.vertexShader = shader.vertexShader.replace(
          '#include <begin_vertex>',
          `
vec3 transformed = vec3( position );
vec2 bonePos = transformed.xy;
for ( int i = 0; i < ${BONE_COUNT}; i ++ ) {
  vec4 bc = uBoneCenter[ i ];
  float weight = 0.0;
  if ( bc.z > 0.0005 ) {
    // 各向异性影响域：沿肢体/面部轴向衰减慢，垂直方向衰减快，权重不外溢到无关区域
    vec4 ba = uBoneAxis[ i ];
    vec2 delta = bonePos - bc.xy;
    vec2 perpendicular = vec2( -ba.y, ba.x );
    vec2 scaled = vec2(
      dot( delta, ba.xy ) / max( ba.z, 0.0001 ),
      dot( delta, perpendicular ) / max( ba.w, 0.0001 )
    );
    // 全半径平滑衰减，而不是「硬核 + 窄过渡带」：
    // 同样位移下局部梯度低得多，形变更流畅、不易出现拉伸扭曲，
    // 因此可以放心用更大的幅度去换更明显的表情。
    float boneDist = clamp( length( scaled ), 0.0, 1.0 );
    weight = ( 1.0 - boneDist * boneDist * ( 3.0 - 2.0 * boneDist ) ) * bc.z;
  }
  vec4 bp = uBonePivot[ i ];
  vec2 rel = bonePos - bp.xy;
  // 缩放（yaw/pitch 的 2.5D 立体感来源）→ 旋转 → 位移
  float boneScaleX = 1.0 + ( uBoneScale[ i ].x - 1.0 ) * weight;
  float boneScaleY = 1.0 + ( uBoneScale[ i ].y - 1.0 ) * weight;
  vec2 shaped = vec2( rel.x * boneScaleX, rel.y * boneScaleY );
  float angle = bp.z * weight;
  float sinA = sin( angle );
  float cosA = cos( angle );
  vec2 spun = vec2( shaped.x * cosA - shaped.y * sinA, shaped.x * sinA + shaped.y * cosA );
  bonePos = bp.xy + spun + uBoneShift[ i ].xy * weight;
}
// 衣物微风：只作用于遮罩覆盖的衣摆与袖摆（裸手已在遮罩中排除）。
// 位移叠在骨骼结果之后，因此与头部/手臂动作同向叠加，不会把身体拉离骨骼。
vec2 clothUv = uv;
float clothWeight = texture2D( uClothMask, clothUv ).r;
float clothEnvelope = smoothstep( 0.05, 0.75, clothWeight );
if ( clothEnvelope > 0.001 ) {
  float gust = sin( uWindTime * 0.85 + bonePos.y * 5.0 )
             + 0.45 * sin( uWindTime * 1.37 + bonePos.x * 7.0 );
  bonePos.x += gust * clothEnvelope * uWindStrength * 0.018;
  bonePos.y += sin( uWindTime * 0.72 + bonePos.x * 4.0 ) * clothEnvelope * uWindStrength * 0.008;
}
transformed = vec3( bonePos, transformed.z );
`,
        )
      }

      const portrait = new THREE.Mesh(new THREE.PlaneGeometry(planeWidth, planeHeight, 110, 160), material)
      root.add(portrait)

      // ---------------- 骨骼布局 ----------------
      const headCenterX = toX(meta.head.x + meta.head.w / 2)
      const headCenterY = toY(meta.head.y + meta.head.h / 2)
      const neckX = toX(meta.neck.x)
      const neckY = toY(meta.neck.y)

      // 头：绕颈枢轴，允许缩放以模拟转头(yaw)/俯仰(pitch)
      boneCenter[HEAD].set(headCenterX, headCenterY, 1, 0)
      bonePivot[HEAD].set(neckX, neckY, 0, 0)
      boneAxis[HEAD].set(0, 1, planeHeight * 0.26, planeHeight * 0.21)

      // 眉：横向较宽、纵向很扁，只影响眉眼区域
      const browY = toY(meta.eyes.left.y - meta.eyes.left.h * 1.4)
      boneCenter[BROW].set(headCenterX, browY, 1, 0)
      bonePivot[BROW].set(headCenterX, toY(meta.head.y + meta.head.h * 0.55), 0, 0)
      boneAxis[BROW].set(1, 0, planeWidth * 0.13, planeHeight * 0.026)

      // 下脸（颊与嘴角）：微笑抬升。
      // 影响域必须避开下巴：原参数（中心在唇线下方 1.5 倍嘴高处、纵向半径 0.075×平面高）
      // 与下颌骨在「唇线～下巴」整段重叠，两块骨一个向上抬、一个向下拉，
      // 净位移在不同位置方向不同 —— 这是"脸部整体不协调"的结构性来源。
      // 现把中心提到唇线、纵向压浅，只作用于嘴角与两颊，与下颌域完全分离。
      const faceY = toY(meta.mouth.y + meta.mouth.h * 0.5)
      boneCenter[FACE].set(headCenterX, faceY, 1, 0)
      bonePivot[FACE].set(headCenterX, toY(meta.head.y + meta.head.h * 1.35), 0, 0)
      boneAxis[FACE].set(1, 0, planeWidth * 0.2, planeHeight * 0.034)

      // 胸腔/肩：呼吸起伏（局部，不是整体位移）
      const bodyX = toX(meta.neck.x)
      const bodyY = toY(meta.neck.y + 0.22)
      boneCenter[BODY].set(bodyX, bodyY, 1, 0)
      bonePivot[BODY].set(bodyX, toY(0.95), 0, 0)
      boneAxis[BODY].set(0, 1, planeHeight * 0.27, planeWidth * 0.38)

      // 双臂：臂骨 + 腕手骨串联
      const layoutArm = (armSlot: number, handSlot: number, side: 'left' | 'right') => {
        const shoulder = meta.shoulders[side]
        const hand = meta.hands[side]?.center ?? {
          x: shoulder.x + (side === 'left' ? -0.15 : 0.15),
          y: shoulder.y + 0.15,
        }
        const shoulderX = toX(shoulder.x)
        const shoulderY = toY(shoulder.y)
        const handX = toX(hand.x)
        const handY = toY(hand.y)
        const spanX = handX - shoulderX
        const spanY = handY - shoulderY
        const span = Math.hypot(spanX, spanY) || 0.001

        // 影响中心下移到靠近手部：手臂几乎垂直下垂时，肩手中点正好落在腰腹附近，
        // 会把腰带与衣料一起拉扯（实测躯干权重 0.65，是"身体扭曲"的直接原因）。
        // 下移后腰带完全落在影响域之外。
        boneCenter[armSlot].set(handX - spanX * 0.15, handY - spanY * 0.15, 1, 0)
        bonePivot[armSlot].set(shoulderX, shoulderY, 0, 0)
        boneAxis[armSlot].set(spanX / span, spanY / span, span * 0.5, span * 0.2)

        boneCenter[handSlot].set(handX, handY, 1, 0)
        bonePivot[handSlot].set(shoulderX + spanX * 0.62, shoulderY + spanY * 0.62, 0, 0)
        boneAxis[handSlot].set(spanX / span, spanY / span, span * 0.38, span * 0.22)
      }
      layoutArm(ARM_L, HAND_L, 'left')
      layoutArm(ARM_R, HAND_R, 'right')

      // 下颌骨：影响域只覆盖唇线到下巴，不触及鼻部与两颊。
      // 原参数（中心在唇线下方 0.9 倍嘴高处、轴向 0.05×平面高、横向 0.15×平面宽）实测：
      //   上唇下沉 19.7px · 唇线 38.3px · 嘴角 30px · 下巴仅 15.6px
      // 即"该动的下巴几乎不动、不该动的上唇与嘴角被拖下去"，整块下脸往下坠。
      // 中心下移到下唇与下巴之间、半径收紧后：下巴 40px · 下唇 37px · 唇线 19px ·
      // 上唇 3px · 鼻尖 0 · 两颊 0，位移顺序与真人的下颌运动一致。
      const jawY = toY(meta.mouth.y + meta.mouth.h * 1.45)
      boneCenter[JAW].set(toX(meta.neck.x), jawY, 1, 0)
      bonePivot[JAW].set(toX(meta.neck.x), toY(meta.mouth.y), 0, 0)
      boneAxis[JAW].set(0, 1, planeHeight * 0.055, planeWidth * 0.085)

      // ---------------- 口型层 ----------------
      // 贴图结构（自上而下）：上唇阴影 → 上齿亮带 → 口腔暗部 → 下唇微光。
      // 单独的对称黑团会被读成"嘴唇上涂了个洞"，上齿亮带是让它读作"张嘴"的关键。
      const mouthCanvas = document.createElement('canvas')
      const MW = 160
      const MH = 128
      mouthCanvas.width = MW
      mouthCanvas.height = MH
      const mouthContext = mouthCanvas.getContext('2d')
      if (mouthContext) {
        // 上唇阴影
        mouthContext.fillStyle = 'rgba(74,34,28,0.4)'
        mouthContext.beginPath()
        mouthContext.ellipse(MW / 2, MH * 0.09, MW * 0.34, MH * 0.085, 0, 0, Math.PI * 2)
        mouthContext.fill()

        // 口腔：宽度约为唇宽的 72%，整体偏下
        const cavity = mouthContext.createRadialGradient(MW / 2, MH * 0.5, MH * 0.02, MW / 2, MH * 0.5, MH * 0.44)
        cavity.addColorStop(0, 'rgba(44,16,16,0.94)')
        cavity.addColorStop(0.62, 'rgba(70,30,28,0.82)')
        cavity.addColorStop(1, 'rgba(70,30,28,0)')
        mouthContext.fillStyle = cavity
        mouthContext.beginPath()
        mouthContext.ellipse(MW / 2, MH * 0.5, MW * 0.36, MH * 0.4, 0, 0, Math.PI * 2)
        mouthContext.fill()

        // 上齿：只是一条细窄的亮带。原实现做成大块高亮椭圆，
        // 看起来是"血盆大口 + 大白牙"，非常惊悚。
        const teeth = mouthContext.createLinearGradient(0, MH * 0.2, 0, MH * 0.38)
        teeth.addColorStop(0, 'rgba(246,240,230,0.6)')
        teeth.addColorStop(1, 'rgba(246,240,230,0)')
        mouthContext.fillStyle = teeth
        mouthContext.beginPath()
        mouthContext.ellipse(MW / 2, MH * 0.27, MW * 0.27, MH * 0.085, 0, 0, Math.PI * 2)
        mouthContext.fill()

        // 下唇微光，让下缘不显生硬
        const lowerLip = mouthContext.createLinearGradient(0, MH * 0.78, 0, MH)
        lowerLip.addColorStop(0, 'rgba(150,86,76,0)')
        lowerLip.addColorStop(1, 'rgba(150,86,76,0.28)')
        mouthContext.fillStyle = lowerLip
        mouthContext.beginPath()
        mouthContext.ellipse(MW / 2, MH * 0.88, MW * 0.3, MH * 0.12, 0, 0, Math.PI * 2)
        mouthContext.fill()
      }
      const mouthTexture = new THREE.CanvasTexture(mouthCanvas)
      mouthTexture.colorSpace = THREE.SRGBColorSpace

      // 最大开口 = 0.45 倍嘴宽 × 视位开口度(A=0.8) = 0.36 倍嘴宽 ≈ 眼裂高的 1.9 倍，
      // 落在真人说话最大开口（2~2.5 倍眼裂高）的区间内。
      mouthBaseHeight = meta.mouth.w * planeWidth * 0.45
      const mouthGeometry = new THREE.PlaneGeometry(meta.mouth.w * planeWidth, mouthBaseHeight)
      // 顶点锚在上唇：张嘴时向下展开（下颌下垂），而不是上下对称扩张顶到鼻子
      mouthGeometry.translate(0, -mouthBaseHeight / 2, 0)
      mouthMesh = new THREE.Mesh(
        mouthGeometry,
        new THREE.MeshBasicMaterial({ map: mouthTexture, transparent: true, opacity: 0, depthWrite: false }),
      )
      mouthMesh.position.z = 0.03
      root.add(mouthMesh)
      overlays.push({
        object: mouthMesh,
        u: meta.mouth.x + meta.mouth.w / 2,
        v: meta.mouth.y + meta.mouth.h / 2 - 0.0045, // 以唇线略上方为上沿
        baseScaleX: () => mouthOwnScale.x,
        baseScaleY: () => mouthOwnScale.y,
      })

      // 眼睛不再用叠加层：改由闭眼素材在着色器里交叉淡入（见 uBlink），
      // 避免"贴皮肤补丁"必然带来的色差与接缝。

      neckPlane.set(neckX, neckY)
    }

    const resize = () => {
      const width = mount.clientWidth || 480
      const height = mount.clientHeight || 620
      renderer.setSize(width, height, false)
      camera.aspect = width / height
      camera.updateProjectionMatrix()
    }
    resize()
    const observer = new ResizeObserver(resize)
    observer.observe(mount)

    // ---------------- 时间与调度状态 ----------------
    let lastTime = performance.now() / 1000
    const startedAt = lastTime
    let gestureKey = stateRef.current.motion
    let gestureStartedAt = startedAt
    let nextBlinkAt = 1.6 + Math.random() * 2.4
    let blinkStartedAt = -1
    let lastBlinkEndAt = 0
    let silenceFor = 0
    let phraseArmed = false
    // 真人眨眼：闭合约 100ms（快）→ 保持 80ms → 张开约 240ms（慢），合计约 0.42s
    const BLINK_CLOSE = 0.1
    const BLINK_HOLD = 0.08
    const BLINK_OPEN = 0.24
    let nextIdleImpulseAt = startedAt + 1.2
    let lastOnsetAt = 0
    let previousMouth = 0
    let raf = 0

    const animate = () => {
      const now = performance.now() / 1000
      const delta = reduceMotion ? 1 / 60 : Math.min(Math.max(now - lastTime, 1 / 240), 0.05)
      lastTime = now
      const elapsed = now - startedAt
      const visual = stateRef.current
      const expression = EMOTIONS[visual.emotion] ?? EMOTIONS.calm
      const energy = reduceMotion ? 0.15 : expression.energy

      if (gestureKey !== visual.motion) {
        gestureKey = visual.motion
        gestureStartedAt = elapsed
      }
      const gesture = elapsed - gestureStartedAt

      // ---------------- 口型（先算，头部重音依赖它）----------------
      const liveMouth = mouthLiveRef.current?.current ?? visual.mouth
      const mouthRaw = visual.speaking ? clamp(liveMouth) : 0
      // 刚度按真实下颌的时间常数设定（比之前慢一倍），音节切换约 190ms 时
      // 下颌来不及完全跟上，自然会形成平滑过渡而不是"每秒数次大张合"
      mouthSpring.stiffness = mouthRaw > mouthSpring.value ? 105 : 80
      mouthSpring.target = mouthRaw
      const mouthValue = reduceMotion ? mouthRaw : mouthSpring.step(delta)

      // 语音信号的三档时间尺度（同源，因此天然同步；时间常数不同，因此有层次）
      mediumEnvSpring.target = mouthValue
      slowEnvSpring.target = mouthValue
      const fastEnv = mouthValue // 音节级：直接用口腔开合，它本身已过嘴部弹簧
      const mediumEnv = reduceMotion ? mouthValue : mediumEnvSpring.step(delta)
      const slowEnv = reduceMotion ? mouthValue : slowEnvSpring.step(delta)

      // 音节起音：驱动点头 / 抬手 / 挑眉等节拍动作。
      // 包络整体放慢，脉冲时长随之拉长，避免"打点"式的急促感。
      const onset = mouthValue - previousMouth
      if (!reduceMotion && onset > 0.16 && elapsed - lastOnsetAt > 0.3) {
        lastOnsetAt = elapsed
        const pick = Math.random()
        if (pick < 0.3) addImpulse('headBob', -0.005 - Math.random() * 0.005, 0.62, elapsed)
        else if (pick < 0.5) addImpulse('armR', 0.06 + Math.random() * 0.05, 0.82, elapsed)
        else if (pick < 0.66) addImpulse('armL', 0.05 + Math.random() * 0.05, 0.82, elapsed)
        else if (pick < 0.84) addImpulse('headYaw', (Math.random() - 0.5) * 0.06, 0.85, elapsed)
        else addImpulse('browRaise', 0.006 + Math.random() * 0.006, 0.75, elapsed)
      }
      previousMouth = mouthValue

      // ---------------- 目标累加 ----------------
      const target: Record<Channel, number> = {
        headYaw: 0,
        headPitch: 0,
        headTilt: 0,
        headBob: 0,
        browRaise: 0,
        browTilt: 0,
        faceLift: 0,
        armL: 0,
        handL: 0,
        armR: 0,
        handR: 0,
      }

      if (!reduceMotion) {
        // ---------------- 待机层：1/f 噪声驱动 ----------------
        // 每个通道用不同的「偏移 + 速度」在同一张噪声表上取样，因此彼此不相关，
        // 但共享 1/f 频谱——既不机械重复，也不像各自独立的正弦那样互不相干。
        // 速度值取不可通约的无理数倍，避免通道之间出现拍频。
        const breathe = Math.sin((elapsed * (Math.PI * 2)) / 4.2)
        const idleAmplitude = (0.78 + 0.22 * pinkAt(37, elapsed, 0.043)) * energy
        const driftA = pinkAt(0, elapsed, 0.21)
        const driftB = pinkAt(311, elapsed, 0.283)
        const driftC = pinkAt(677, elapsed, 0.167)

        target.headYaw += (0.082 * driftA + 0.045 * driftB) * idleAmplitude
        target.headPitch += (0.055 * driftB + 0.031 * driftC) * idleAmplitude
        target.headTilt += (0.031 * driftC + 0.017 * driftA) * idleAmplitude
        target.headBob += 0.01 * driftA * idleAmplitude
        // 眉与头取不同偏移：眉毛的活动与头部不完全同步，这是"次级动作"
        target.browRaise += expression.browRaise + 0.019 * pinkAt(911, elapsed, 0.243)
        target.browTilt += expression.browTilt + 0.019 * pinkAt(1201, elapsed, 0.191)
        target.faceLift = expression.faceLift
        target.armL += (0.056 * driftB + 0.034 * driftC) * idleAmplitude
        target.armR += (0.052 * pinkAt(433, elapsed, 0.227) + 0.031 * driftB) * idleAmplitude

        // 呼吸：胸腔扩张 + 上抬（局部）
        boneScale[BODY].x = 1 + 0.007 * breathe
        boneScale[BODY].y = 1 + 0.005 * breathe
        boneShift[BODY].y = 0.012 * breathe

        // ---------------- 语音驱动层 ----------------
        // 全部源自同一路语音信号（同源 → 天然同步），但各自时间尺度不同（→ 有层次）。
        // 上一版把三档压成一条慢包络，结果整张脸被"平均"成凝固姿态，是退步。
        const fast = clamp(fastEnv) // 音节级 ≈0.19s
        const medium = clamp(mediumEnv) // 短语内起伏 ≈0.3s
        const slow = clamp(slowEnv) // 姿态基准 ≈0.9s

        // 头：短语级为主（头部是"慢载体"），音节级只留很小的响应。
        // 原来 headBob / headPitch 的 fast 项偏大，头跟着每个音节一起抖，
        // 与嘴部的音节级细节同频 —— 面部少了"慢承载 + 快细节"的层次。
        target.headBob -= fast * 0.018
        target.headPitch += fast * 0.022 - medium * 0.055
        target.headYaw += medium * 0.06 + slow * 0.035
        // 眉：走短语级重音，不跟每个音节。原来含 fast 项，眉毛逐音节抖动，
        // 是面部唯一"高频独立"的一路，也是整体不协调的来源之一。
        // 仍读取 45ms 之前的信号，保留一点次级动作。
        browDelay.push(elapsed, medium)
        const mediumLag = browDelay.read(elapsed, 0.045)
        target.browRaise += mediumLag * 0.055 + slow * 0.02
        target.browTilt += mediumLag * 0.014
        // 下脸：只做情绪性的微笑抬升，且走短语级。
        // 原来叠加 medium*0.42 + fast*0.3，说话时 faceLift 从情绪基准一路抬到 0.96，
        // 等于每次开口都伴随一个持续的大笑抬升，正好与下颌的下沉对抗、互相抵消。
        target.faceLift = Math.min(1.0, expression.faceLift + medium * 0.14 + slow * 0.1)
        // 手只做很小的基准抬起 + 音节级微动；
        // 大幅抬手交给下面的「短语边界手势」，否则会抬起来定在半空。
        const armSway = Math.sin(elapsed * 0.33)
        target.armL += slow * 0.12 + fast * 0.13 + slow * 0.05 * armSway
        target.armR += slow * 0.11 + fast * 0.13 - slow * 0.05 * armSway

        // 短语边界手势：静音一段时间后重新起音 → 抬一次手再自然回落。
        // 这与说话的段落节奏一致，比"全程抬起"自然得多。
        if (mouthValue < 0.1) phraseArmed = true
        else if (phraseArmed) {
          phraseArmed = false
          addImpulse('armL', 0.2 + Math.random() * 0.16, 1.6 + Math.random() * 0.8, elapsed)
          addImpulse('armR', 0.18 + Math.random() * 0.16, 1.6 + Math.random() * 0.8, elapsed)
          addImpulse('browRaise', 0.01 + Math.random() * 0.008, 0.95, elapsed)
        }

        // ---------------- 手势编排 ----------------
        if (visual.motion === 'wave') {
          const lift = easeOutCubic(clamp(gesture / 0.34))
          const settleAt = 2.5
          const settle = gesture > settleAt ? easeInOutQuad(clamp((gesture - settleAt) / 0.55)) : 0
          const inSwing = gesture > 0.26 && gesture < settleAt
          const progress = clamp((gesture - 0.26) / (settleAt - 0.26))
          const swing = inSwing ? shapeBeat(Math.sin(progress * Math.PI * 4.6)) * (1 - 0.28 * progress) : 0
          target.armR += (0.62 * lift - 0.26 * settle) * (1 - 0.35 * settle)
          target.armL += 0.2 * lift + 0.06 * swing
          target.armR -= 0.07 * anticipation(gesture, 0.24) // 抬手先有个下压准备
          target.headYaw += 0.12 * lift
          target.headTilt += 0.012 * swing
          target.headBob += 0.006 * lift + 0.0035 * Math.abs(swing)
          target.browRaise += 0.012 * lift
          target.faceLift = Math.max(target.faceLift, 0.4 * lift)
        } else if (visual.motion === 'greet') {
          const lift = easeOutCubic(clamp(gesture / 0.32))
          const swing = gesture > 0.24 ? shapeBeat(Math.sin((gesture - 0.24) * 4.2)) * 0.85 : 0
          target.armR += 0.5 * lift + 0.12 * swing
          target.armL += 0.24 * lift
          target.headYaw += 0.1 * lift
          target.headBob += 0.007 * lift + 0.0035 * swing
          target.browRaise += 0.01 * lift
          target.faceLift = Math.max(target.faceLift, 0.45 * lift)
        } else if (visual.motion === 'nod') {
          const cycle = 0.95
          const phase = (gesture % cycle) / cycle
          const amount = phase < 0.3 ? easeInQuad(phase / 0.3) : 1 - easeOutQuad((phase - 0.3) / 0.7)
          target.headPitch += 0.19 * amount - 0.055 * anticipation(gesture, 0.2) // 先微微抬头再点头
          target.headBob -= 0.013 * amount
          target.headTilt -= 0.009 * amount
          target.faceLift = Math.max(target.faceLift, 0.15)
        } else if (visual.motion === 'shake') {
          const cycle = 0.98
          const phase = (gesture % cycle) / cycle
          const amount = phase < 0.38 ? easeInOutQuad(phase / 0.38) : 1 - easeInOutQuad((phase - 0.38) / 0.62)
          target.headYaw += shapeBeat(Math.sin(gesture * 6.6)) * 0.34 * amount
          target.headYaw += 0.05 * anticipation(gesture, 0.22) // 摇头前先反向微摆
          target.browRaise -= 0.004 * amount
        } else if (visual.motion === 'point') {
          const lift = easeOutCubic(clamp(gesture / 0.4))
          target.armL += 0.55 * lift + 0.022 * Math.sin(elapsed * 0.31)
          target.armR += 0.15 * lift
          target.headYaw -= 0.11 * lift
          target.headPitch += 0.03 * lift
          target.browRaise += 0.008 * lift
        }
        // 讲解 / 说话不再单独驱动手臂：上面的语音驱动层已经让双手随语音能量上抬，
        // 且与眉、头、下巴同源，避免了"手在跳、脸在僵"的割裂。

        // ---------------- 微动作脉冲调度 ----------------
        if (elapsed > nextIdleImpulseAt) {
          const roll = Math.random()
          if (roll < 0.24) addImpulse('headYaw', (Math.random() - 0.5) * 0.15, 1.9 + Math.random() * 1.4, elapsed)
          else if (roll < 0.44) addImpulse('headPitch', (Math.random() - 0.5) * 0.1, 1.7 + Math.random() * 1.2, elapsed)
          else if (roll < 0.58) addImpulse('headTilt', (Math.random() - 0.5) * 0.014, 2.0 + Math.random() * 1.2, elapsed)
          else if (roll < 0.7) addImpulse('browRaise', 0.007 + Math.random() * 0.009, 1.0 + Math.random() * 0.8, elapsed)
          // 手臂小调整：像站立时把手往上带一下，给待机加入肢体层次
          else if (roll < 0.85) addImpulse('armR', 0.07 + Math.random() * 0.07, 2.0 + Math.random() * 1.3, elapsed)
          else if (roll < 0.95) addImpulse('armL', 0.06 + Math.random() * 0.06, 2.0 + Math.random() * 1.3, elapsed)
          else addImpulse('headBob', -0.005, 1.1, elapsed)
          nextIdleImpulseAt = elapsed + 4.5 + Math.random() * 6.5
        }
        for (let index = impulses.length - 1; index >= 0; index -= 1) {
          const impulse = impulses[index]
          const progress = (elapsed - impulse.start) / impulse.duration
          if (progress >= 1) {
            impulses.splice(index, 1)
            continue
          }
          if (progress < 0) continue
          // 平滑起落包络，避免脉冲两端出现折角
          target[impulse.channel] += impulse.amount * Math.sin(Math.PI * progress)
        }
      }

      // ---------------- 弹簧积分 ----------------
      for (const key of Object.keys(springs) as Channel[]) springs[key].target = target[key]
      const headYaw = springs.headYaw.step(delta)
      const headPitch = springs.headPitch.step(delta)
      const headTilt = springs.headTilt.step(delta)
      const headBob = springs.headBob.step(delta)
      const browRaise = springs.browRaise.step(delta)
      const browTilt = springs.browTilt.step(delta)
      const faceLift = springs.faceLift.step(delta)
      const armL = springs.armL.step(delta)
      const armR = springs.armR.step(delta)

      armDelay.push(elapsed, armR)
      const handLag = reduceMotion ? 0 : 0.075
      // 腕手读取延迟后的臂部目标并放大 → 抬手时手比手臂多走一点、晚到一点
      springs.handR.target = armR * 0.5 + armDelay.read(elapsed, handLag) * 1.2 * 0.55 + mouthValue * 0.03
      springs.handL.target = armL * 0.5 + armDelay.read(elapsed, handLag + 0.02) * 1.1 * 0.55 + mouthValue * 0.025
      const handL = springs.handL.step(delta)
      const handR = springs.handR.step(delta)

      // ---------------- 写入骨骼 ----------------
      // 头：yaw 收窄+横移，pitch 压扁+纵移，加上平面内倾斜
      bonePivot[HEAD].z = headTilt
      // 转头/俯仰的收窄压到 3~5%：2D 形变一旦超过约 5%，脸就不再被读作"一张脸"
      boneScale[HEAD].x = 1 - 0.05 * Math.abs(headYaw)
      boneScale[HEAD].y = 1 - 0.035 * Math.abs(headPitch)
      boneShift[HEAD].x = headYaw * planeWidth * 0.06
      // 弧线运动（动画十二法则）：纯线性位移让头走直线、显得机械；
      // 把横向偏移耦合一点纵向分量，头部便沿弧线移动，两侧端点自然略沉。
      boneShift[HEAD].y =
        headBob + headPitch * planeHeight * 0.045 + Math.abs(headYaw) * planeHeight * 0.009

      bonePivot[BROW].z = browTilt
      boneShift[BROW].y = browRaise * planeHeight * 0.115
      boneScale[BROW].y = 1 - 0.1 * Math.abs(browTilt) * 6

      // 下脸只做约 1px 的抬升与 0.3% 的形变，仅作为生命感点缀
      boneShift[FACE].y = faceLift * planeHeight * 0.006
      boneScale[FACE].x = 1 + 0.008 * faceLift
      boneScale[FACE].y = 1 + 0.004 * faceLift

      // 双臂几乎垂直下垂时，绕肩旋转只能左右摆动、抬不起手，
      // 所以主通道改为「上提位移」，旋转只作为小角度外摆的辅助。
      const liftUnit = planeHeight * 0.075
      boneShift[ARM_L].x = -armL * planeWidth * 0.012
      boneShift[ARM_L].y = armL * liftUnit * 0.3
      boneShift[HAND_L].x = -handL * planeWidth * 0.022
      boneShift[HAND_L].y = handL * liftUnit
      bonePivot[ARM_L].z = -armL * 0.12
      bonePivot[HAND_L].z = -handL * 0.1
      boneShift[ARM_R].x = armR * planeWidth * 0.012
      boneShift[ARM_R].y = armR * liftUnit * 0.3
      boneShift[HAND_R].x = handR * planeWidth * 0.022
      boneShift[HAND_R].y = handR * liftUnit
      bonePivot[ARM_R].z = armR * 0.12
      bonePivot[HAND_R].z = handR * 0.1

      // ---------------- 口型形状 ----------------
      const viseme = visemeLiveRef.current?.current
      const shape = VISEME_SHAPE[viseme ?? 'sil'] ?? [1, 1]
      // 不加逐帧随机抖动：高频噪点会让嘴唇发抖，明显不自然
      const openness = Math.max(0.001, mouthValue)
      // 宽高比也过弹簧：否则视位一换嘴形就硬跳，这是"不自然"的主要来源之一
      mouthWidthSpring.target = shape[0]
      mouthHeightSpring.target = shape[1]
      const shapeWidth = mouthWidthSpring.step(delta)
      const shapeHeight = mouthHeightSpring.step(delta)
      mouthOwnScale.set((0.78 + openness * 0.36) * shapeWidth, openness * shapeHeight)

      // 下颌下沉量由「实际开口高度」推出，而不是只看开口度。
      // 之前用 mouthValue 单独驱动下颌，而嘴唇张开量是 mouthValue × 视位高比：
      // 遇到扁唇视位（I=0.68 / E=0.82）或闭唇视位（M=0.45）时，下巴的动幅是唇缝
      // 张开量的 1.5~2.5 倍——下巴一开一合、嘴唇几乎不动，是面部不协调的直接来源。
      // 改为与叠加层同源，下巴永远比唇缝多下沉约 11%，两者不可能再失配。
      boneShift[JAW].y = -mouthBaseHeight * openness * shapeHeight * 1.11
      if (mouthMesh) {
        // 透明度跟随开口度：闭口帧（视位 sil/M）几乎不可见，避免残留一道暗痕
        const material = mouthMesh.material as THREE.MeshBasicMaterial
        material.opacity = visual.speaking ? Math.min(0.88, 0.1 + openness * 0.85) : 0
      }

      // ---------------- 眨眼 / 微笑眯眼 ----------------
      let blink = 0
      if (!reduceMotion) {
        // 说话时把眨眼压在短语停顿处——真实说话人就是在停顿时眨眼。
        // 原实现用独立随机定时器，与语音毫无关系，这是"眼睛和嘴各走各的"的根源。
        if (visual.speaking && mouthValue > 0.02) {
          if (mouthValue < 0.1) silenceFor += delta
          else silenceFor = 0
          if (silenceFor > 0.14 && blinkStartedAt < 0 && elapsed - lastBlinkEndAt > 1.3) {
            blinkStartedAt = elapsed
            silenceFor = 0
          }
        } else if (blinkStartedAt < 0 && elapsed > nextBlinkAt) {
          blinkStartedAt = elapsed
        }
        if (blinkStartedAt >= 0) {
          const passed = elapsed - blinkStartedAt
          if (passed >= BLINK_CLOSE + BLINK_HOLD + BLINK_OPEN) {
            blinkStartedAt = -1
            lastBlinkEndAt = elapsed
            nextBlinkAt = elapsed + 2.6 + Math.random() * 3.8
          } else if (passed < BLINK_CLOSE) {
            blink = easeInQuad(passed / BLINK_CLOSE)
          } else if (passed < BLINK_CLOSE + BLINK_HOLD) {
            blink = 1 // 闭眼保持相：缺少这一段会显得眼皮一闪而过
          } else {
            blink = 1 - easeOutQuad((passed - BLINK_CLOSE - BLINK_HOLD) / BLINK_OPEN)
          }
        }
      }
      // 闭眼素材的混合权重：眨眼取瞬时值，情绪带来的静态眯眼（真诚微笑的关键）作为下限
      const squint = reduceMotion ? 0 : expression.squint
      blinkUniform.value = Math.min(1, Math.max(blink, squint))

      // ---------------- 叠加层跟随面部骨骼链 ----------------
      // 关键修正：叠加层此前只跟「头骨」，且权重硬编码为 1；而下颌骨会让嘴周随开口
      // 下沉（boneShift[JAW].y 达 0.03×平面高，几乎等于整个嘴的高度）。于是网格的嘴
      // 在动、贴上去的口型层不动 —— 这正是"回答问题时嘴巴与面部脱离"的原因。
      // 改为在 JS 侧镜像顶点着色器的骨骼累加，使叠加层与网格经历完全相同的变换。
      if (overlays.length) {
        const boneWeightAt = (slot: number, x: number, y: number) => {
          const center = boneCenter[slot]
          if (center.z <= 0.0005) return 0
          const axis = boneAxis[slot]
          const dx = x - center.x
          const dy = y - center.y
          const along = (dx * axis.x + dy * axis.y) / Math.max(axis.z, 0.0001)
          const perpendicular = (-dx * axis.y + dy * axis.x) / Math.max(axis.w, 0.0001)
          const distance = Math.min(1, Math.hypot(along, perpendicular))
          return (1 - distance * distance * (3 - 2 * distance)) * center.z
        }

        /** 与着色器一致：按骨骼顺序链式变换（缩放 → 旋转 → 位移），量与角度按权重插值 */
        const posePoint = (x: number, y: number) => {
          let px = x
          let py = y
          let angleSum = 0
          let scaleX = 1
          let scaleY = 1
          for (let slot = 0; slot < BONE_COUNT; slot += 1) {
            if (boneCenter[slot].z <= 0.0005) continue
            const weight = boneWeightAt(slot, px, py)
            const pivot = bonePivot[slot]
            const relX = px - pivot.x
            const relY = py - pivot.y
            const sx = 1 + (boneScale[slot].x - 1) * weight
            const sy = 1 + (boneScale[slot].y - 1) * weight
            const angle = pivot.z * weight
            const cosine = Math.cos(angle)
            const sine = Math.sin(angle)
            const shapedX = relX * sx
            const shapedY = relY * sy
            px = pivot.x + shapedX * cosine - shapedY * sine + boneShift[slot].x * weight
            py = pivot.y + shapedX * sine + shapedY * cosine + boneShift[slot].y * weight
            angleSum += angle
            scaleX *= sx
            scaleY *= sy
          }
          return { x: px, y: py, angle: angleSum, scaleX, scaleY }
        }

        for (const item of overlays) {
          const posed = posePoint((item.u - 0.5) * planeWidth, (0.5 - item.v) * planeHeight)
          item.object.position.x = posed.x
          item.object.position.y = posed.y
          item.object.rotation.z = posed.angle
          item.object.scale.set(item.baseScaleX() * posed.scaleX, item.baseScaleY() * posed.scaleY, 1)
        }
      }

      // ---------------- 衣物微风 ----------------
      // 时间必须用 elapsed（而非 now）：它以第一帧为基准，避免长时间运行时 sin 的
      // 浮点精度退化导致风感突然凝固。强度待机 0.55、动作期 0.8，减少动画时为 0。
      if (assetsRef.current.clothMask) {
        windTimeUniform.value = elapsed
        const activeMotion = visual.motion === 'wave' || visual.motion === 'greet'
        windStrengthUniform.value = reduceMotion ? 0 : activeMotion || visual.motion === 'point' || visual.motion === 'explain' ? 0.8 : 0.55
      } else {
        windStrengthUniform.value = 0
      }

      // ---------------- 整体：呼吸 + 重心微移（允许细微身体起伏）----------------
      if (!reduceMotion) {
        const breathe = Math.sin((elapsed * (Math.PI * 2)) / 3.9 + 0.9)
        const shift = Math.sin((elapsed * (Math.PI * 2)) / 11.5)
        root.position.y = 0.006 * breathe
        root.position.x = 0.006 * shift
        root.scale.setScalar(1 + 0.0015 * breathe)
        root.rotation.z = 0.0025 * shift
      }

      renderer.render(scene, camera)
      raf = requestAnimationFrame(animate)
    }
    animate()

    return () => {
      cancelAnimationFrame(raf)
      observer.disconnect()
      scene.traverse((object) => {
        if (object instanceof THREE.Mesh) {
          object.geometry?.dispose?.()
          const material = object.material
          if (Array.isArray(material)) material.forEach((item) => item.dispose())
          else material?.dispose?.()
        }
      })
      renderer.dispose()
      if (renderer.domElement.parentNode === mount) mount.removeChild(renderer.domElement)
    }
  }, [assets.status])

  return (
    <div className="relative w-full">
      {/* 舞台本体：无底色、无边框、无装饰，画面中只有人物 */}
      <div ref={mountRef} className="h-[min(64vh,660px)] w-full" />

      {assets.status !== 'ready' && (
        <div className="absolute inset-0 grid place-content-center px-8 text-center">
          <p className="text-[13px] leading-relaxed text-ink-3">
            {assets.status === 'loading' ? '正在加载数字人形象…' : '数字人形象资产未就绪'}
          </p>
          {assets.error && <p className="mt-2 max-w-md text-[11.5px] leading-relaxed text-ink-4">{assets.error}</p>}
        </div>
      )}
    </div>
  )
}
