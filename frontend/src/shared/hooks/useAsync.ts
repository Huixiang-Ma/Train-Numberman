/**
 * 工单16-20 延伸 · 平台化双端重构（批次 1）
 * 只读请求的三态封装：加载中 / 成功 / 失败。
 *
 * 为什么不用数据请求库：全站只读请求形态单一（进页面取一次、条件变了重取），
 * 引入 TanStack Query 属过度设计（docs/08 §4.3 已明确不引入）。
 *
 * 依赖用一个**序列化字符串 key** 而不是数组：后者需要调用方自己保证
 * 数组长度与顺序稳定，改一处就容易漏触发或反复触发。
 */
import { useCallback, useEffect, useRef, useState } from 'react'

export type AsyncState<T> = { kind: 'loading' } | { kind: 'ready'; data: T } | { kind: 'error'; message: string }

export function useAsync<T>(loader: () => Promise<T>, key = '') {
  const [state, setState] = useState<AsyncState<T>>({ kind: 'loading' })
  const [tick, setTick] = useState(0)
  // 用 ref 持有最新的 loader，避免把函数放进依赖导致每次渲染都重新请求
  const loaderRef = useRef(loader)
  loaderRef.current = loader

  useEffect(() => {
    let alive = true
    setState({ kind: 'loading' })
    loaderRef
      .current()
      .then((data) => {
        if (alive) setState({ kind: 'ready', data })
      })
      .catch((error: unknown) => {
        // 组件已卸载（或 key 已变）时就不要再写入状态，否则会更新到废弃的实例上
        if (!alive) return
        setState({ kind: 'error', message: error instanceof Error ? error.message : String(error) })
      })
    return () => {
      alive = false
    }
  }, [key, tick])

  const reload = useCallback(() => setTick((value) => value + 1), [])
  return { state, reload }
}
