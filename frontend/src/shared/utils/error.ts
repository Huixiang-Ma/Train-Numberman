/**
 * 工单16-20 延伸 · 错误文案归一（批次 4）
 *
 * 为什么收口成一处：api/client.ts 抛出的 Error 已经是后端 message/detail 的可读文案，
 * 但 catch 到的值是 unknown，各页面自行 `err instanceof Error ? err.message : String(err)`
 * 会逐渐写出不一致的兜底文案（有的显示 "unknown"，有的直接空字符串）。
 */
export function apiErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    if (!error.message) return '请求失败，请稍后重试'
    // fetch 在网络不通时抛 "Failed to fetch"，对运营人员没有信息量
    if (/failed to fetch|networkerror|load failed/i.test(error.message)) {
      return '无法连接后端，请确认服务已启动（默认 8100 端口）'
    }
    return error.message
  }
  return String(error) || '未知错误'
}
