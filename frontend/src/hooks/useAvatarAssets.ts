import { useEffect, useState } from 'react'

export interface AvatarBox {
  x: number
  y: number
  w: number
  h: number
}

export interface AvatarPoint {
  x: number
  y: number
}

export interface AvatarHand extends AvatarBox {
  side: 'left' | 'right'
  index: number
  wrist: AvatarPoint
  center: AvatarPoint
}

export interface AvatarAssetMeta {
  image: string
  /** 眨眼贴图：RGB 为闭眼画面，alpha 为「眨眼影响区域」（只在眼睛附近生效） */
  blink_image?: string
  width: number
  height: number
  /** 嘴部叠加层区域（口型开合用） */
  mouth: AvatarBox
  /** 双眼区域（眨眼用） */
  eyes: { left: AvatarBox; right: AvatarBox }
  /** 头部区域 */
  head: AvatarBox
  /** 颈部枢轴（头部动作的旋转中心） */
  neck: AvatarPoint
  /** 双肩枢轴（手臂动作的旋转中心） */
  shoulders: { left: AvatarPoint; right: AvatarPoint }
  /** 双手位置（肢体动作的影响中心） */
  hands: { left: AvatarHand | null; right: AvatarHand | null }
  /** 衣物微风遮罩路径（可选；缺省时按 /avatar/{id}-cloth-mask.png 约定查找） */
  cloth_mask?: string
  source: string
}

export interface AvatarAssets {
  meta: AvatarAssetMeta | null
  texture: HTMLImageElement | null
  /** 闭眼素材（缺省时不眨眼，不影响其余动作） */
  blink: HTMLImageElement | null
  /**
   * 衣物微风遮罩（缺省时关闭风感，不影响其余动作）。
   * 与形象图同尺寸的灰度图：255 表示该像素属于衣摆/袖摆。
   */
  clothMask: HTMLImageElement | null
  status: 'loading' | 'ready' | 'missing'
  error: string | null
}

/** 载入图片，失败返回 null（可选素材不应阻断形象加载） */
async function loadImage(src: string, optional = false): Promise<HTMLImageElement | null> {
  const image = new Image()
  image.src = src
  try {
    await new Promise<void>((resolve, reject) => {
      image.onload = () => resolve()
      image.onerror = () => reject(new Error(`图片加载失败：${src}`))
    })
    return image
  } catch (error) {
    if (optional) return null
    throw error
  }
}

/**
 * 工单18 · 加载数字人形象资产
 * 资产由 backend/scripts 产出：透明底形象图 + 关键点坐标 + 闭眼贴图。
 */
export function useAvatarAssets(avatarId = 'qingci'): AvatarAssets {
  const [state, setState] = useState<AvatarAssets>({
    meta: null,
    texture: null,
    blink: null,
    clothMask: null,
    status: 'loading',
    error: null,
  })

  useEffect(() => {
    let cancelled = false

    const load = async () => {
      try {
        const response = await fetch(`/avatar/${avatarId}.json`, { cache: 'no-cache' })
        if (!response.ok) {
          throw new Error(`形象资产未就绪（缺少 /avatar/${avatarId}.json），请运行 backend/scripts/prepare_avatar.py`)
        }
        const meta = (await response.json()) as AvatarAssetMeta

        const image = await loadImage(meta.image)
        if (!image) throw new Error(`形象图片加载失败：${meta.image}`)
        const blink = meta.blink_image ? await loadImage(meta.blink_image, true) : null
        // 遮罩由 backend/scripts/build_cloth_mask.py 派生；缺失只是少了风感，不是形象不可用
        const clothMaskSrc = meta.cloth_mask ?? `/avatar/${avatarId}-cloth-mask.png`
        const clothMask = await loadImage(clothMaskSrc, true)

        if (!cancelled) setState({ meta, texture: image, blink, clothMask, status: 'ready', error: null })
      } catch (error) {
        if (!cancelled) {
          setState({
            meta: null,
            texture: null,
            blink: null,
            clothMask: null,
            status: 'missing',
            error: (error as Error).message,
          })
        }
      }
    }

    void load()
    return () => {
      cancelled = true
    }
  }, [avatarId])

  return state
}
