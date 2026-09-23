/**
 * docs/09 G5 · 游客需求洞察（批次 6）
 *
 * 工单16 §2.1 第 4 条要求「通过数据分析工具精准洞察游客需求」，但工单原文
 * **没有定义任何指标**。本页是项目自行补充的定义，因此每一块都标注了计算口径，
 * 避免验收时对"这个数字怎么来的"产生争议：
 *   · 意图分布 → 后端 DialogService 的判定结果（不是前端猜测）
 *   · 热点词   → 中文二元组词频（未引入分词器）
 *   · 涉及景区 → 景区名在问题文本中的字符串命中（非语义归属）
 *
 * 「知识库盲区」是这一页真正有行动价值的那块：引文数为 0 的问题，
 * 逐条就是知识库该补的内容清单。
 */
import { useState } from 'react'
import { api } from '../../../api/client'
import { BarList, GapNotice, RatioRing, TrendLine } from '../../../shared/components/MiniChart'
import PageHeader from '../../../shared/components/PageHeader'
import StateView from '../../../shared/components/StateView'
import { useAsync } from '../../../shared/hooks/useAsync'
import { TONE_CLASS } from '../../../shared/utils/tone'

const DAY_OPTIONS = [7, 30, 90]

export default function InsightPage() {
  const [days, setDays] = useState(30)
  const insight = useAsync(() => api.analyticsInsight(days), String(days))

  return (
    <div>
      <PageHeader
        tone="cool"
        title="游客需求洞察"
        desc="游客在问什么、问得对不对、知识库缺什么（工单16 §2.1 第 4 条）"
        extra={
          <>
            <div className="scroll-x">
              {DAY_OPTIONS.map((option) => (
                <button
                  key={option}
                  onClick={() => setDays(option)}
                  className={`rounded-full border px-3 py-1.5 text-[12px] ${
                    days === option
                      ? 'border-steel/45 bg-steel/10 font-medium text-steel-deep'
                      : 'border-cool-line bg-cool-surface-2 text-cool-ink-3'
                  }`}
                >
                  近 {option} 天
                </button>
              ))}
            </div>
            <button
              onClick={insight.reload}
              className="rounded-lg border border-cool-line bg-cool-surface px-3 py-1.5 text-[12.5px] text-cool-ink-2 hover:border-steel/40 hover:text-steel-deep"
            >
              刷新
            </button>
          </>
        }
      />

      <StateView state={insight.state} tone="cool" loadingText="正在汇总提问记录…" onRetry={insight.reload}>
        {(data) => (
          <div className="flex flex-col gap-4">
            {/* 概览 */}
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              {[
                { label: '累计提问', value: data.total.toLocaleString() },
                { label: `近 ${data.days} 天`, value: data.recent.toLocaleString() },
                { label: '多模态占比', value: `${(data.multimodal_ratio * 100).toFixed(1)}%` },
                { label: '平均响应', value: data.avg_latency_ms == null ? '—' : `${(data.avg_latency_ms / 1000).toFixed(2)} 秒` },
              ].map((item) => (
                <div key={item.label} className="rounded-xl border border-cool-line bg-cool-surface px-3.5 py-3 shadow-console">
                  <div className="text-[11.5px] text-cool-ink-3">{item.label}</div>
                  <div className="mt-0.5 text-[19px] font-semibold text-cool-ink">{item.value}</div>
                </div>
              ))}
            </div>

            <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
              {/* 意图分布 */}
              <section className="rounded-xl border border-cool-line bg-cool-surface p-4 shadow-console">
                <h2 className="mb-1 text-[13px] font-medium text-cool-ink">检索意图分布</h2>
                <p className="mb-3 text-[11px] leading-relaxed text-cool-ink-4">
                  口径：后端 DialogService 的意图判定结果，非前端猜测。「未分类」多为纯检索问答（不经过对话意图识别）。
                </p>
                {data.intents.length === 0 ? (
                  <RatioRing
                    label="暂无提问记录"
                    ratio={0}
                    caption={`query_log 自批次 6 起才开始记录，刚部署时本页为空属正常，不是故障。`}
                  />
                ) : (
                  <BarList
                    data={data.intents.map((item) => ({
                      label: item.label,
                      value: item.count,
                      hint: `${(item.share * 100).toFixed(1)}%`,
                    }))}
                    unit=" 次"
                  />
                )}

                <div className="mt-4 border-t border-cool-line pt-3">
                  <h3 className="mb-2 text-[12.5px] font-medium text-cool-ink">来源分布</h3>
                  <BarList
                    data={data.sources.map((item) => ({
                      label: item.source === 'dialog' ? '数字人对话' : '检索问答',
                      value: item.count,
                    }))}
                    unit=" 次"
                    tone="amber"
                  />
                </div>
              </section>

              {/* 热点与景区 */}
              <section className="rounded-xl border border-cool-line bg-cool-surface p-4 shadow-console">
                <h2 className="mb-1 text-[13px] font-medium text-cool-ink">提问热点</h2>
                <p className="mb-3 text-[11px] leading-relaxed text-cool-ink-4">{data.hot_word_method}</p>
                {data.hot_words.length === 0 ? (
                  <div className="rounded-lg border border-dashed border-cool-line bg-cool-bg px-3 py-6 text-center text-[11.5px] text-cool-ink-3">
                    热点词需同一词汇出现 2 次以上才计入，当前样本不足
                  </div>
                ) : (
                  <div className="flex flex-wrap items-center gap-1.5">
                    {data.hot_words.map((item, index) => (
                      <span
                        key={item.word}
                        // 字号随词频递增：让高频词在视觉上先跳出来
                        style={{ fontSize: `${Math.min(15, 11 + index * 0.4)}px` }}
                        className={`rounded-full border px-2.5 py-1 ${
                          index < 3
                            ? 'border-steel/45 bg-steel/10 font-medium text-steel-deep'
                            : 'border-cool-line bg-cool-surface-2 text-cool-ink-3'
                        }`}
                      >
                        {item.word}
                        <span className="ml-1 text-[10px] text-cool-ink-4">{item.count}</span>
                      </span>
                    ))}
                  </div>
                )}

                <div className="mt-4 border-t border-cool-line pt-3">
                  <h3 className="mb-1 text-[12.5px] font-medium text-cool-ink">问题涉及的景区</h3>
                  <p className="mb-2.5 text-[11px] text-cool-ink-4">{data.park_mention_method}</p>
                  <BarList
                    data={data.park_mentions.map((item) => ({ label: item.park_name, value: item.count }))}
                    unit=" 次"
                    tone="clay"
                  />
                </div>
              </section>
            </div>

            {/* 趋势 */}
            <section className="rounded-xl border border-cool-line bg-cool-surface p-4 shadow-console">
              <h2 className="mb-3 text-[13px] font-medium text-cool-ink">提问趋势（近 {data.days} 天）</h2>
              <TrendLine data={data.trend.map((item) => ({ label: item.date.slice(5), value: item.count }))} unit=" 次" />
            </section>

            {/* 知识库盲区 */}
            <section className="rounded-xl border border-cool-line bg-cool-surface p-4 shadow-console">
              <div className="mb-1 flex flex-wrap items-baseline gap-2">
                <h2 className="text-[13px] font-medium text-cool-ink">知识库盲区</h2>
                <span className={`rounded-full border px-2 py-0.5 text-[10.5px] ${data.blind_spots.length > 0 ? TONE_CLASS.warn : TONE_CLASS.ok}`}>
                  {data.blind_spots.length} 条检索无命中
                </span>
              </div>
              <p className="mb-3 text-[11px] leading-relaxed text-cool-ink-4">
                判定标准：引文数为 0。这一栏是**可直接执行的补充清单**，
                比任何热度排名都更能改善数字人的回答质量。
              </p>
              {data.blind_spots.length === 0 ? (
                <div className="rounded-lg border border-dashed border-cool-line bg-cool-bg px-3 py-6 text-center text-[11.5px] text-cool-ink-3">
                  近期没有检索落空的问题
                </div>
              ) : (
                <ul className="flex flex-col gap-1.5">
                  {data.blind_spots.slice(0, 8).map((item, index) => (
                    <li key={`${item.question}-${index}`} className="flex items-start gap-2 rounded-lg border border-amber/35 bg-amber/10 px-3 py-2">
                      <span className="mt-[3px] h-1.5 w-1.5 shrink-0 rounded-full bg-amber" />
                      <div className="min-w-0">
                        <div className="text-[12.5px] text-cool-ink">{item.question}</div>
                        {item.created_at && (
                          <div className="mt-0.5 text-[10.5px] text-cool-ink-4">
                            {item.created_at.replace('T', ' ').slice(0, 16)}
                          </div>
                        )}
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            {/* 最近提问 */}
            <section className="rounded-xl border border-cool-line bg-cool-surface p-4 shadow-console">
              <h2 className="mb-3 text-[13px] font-medium text-cool-ink">最近提问（最多 30 条）</h2>
              {data.recent_questions.length === 0 ? (
                <div className="rounded-lg border border-dashed border-cool-line bg-cool-bg px-3 py-6 text-center text-[11.5px] text-cool-ink-3">
                  还没有提问记录
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full border-collapse text-[12px]">
                    <thead>
                      <tr className="text-left text-cool-ink-3">
                        <th className="py-1.5 pr-3 font-medium">问题</th>
                        <th className="py-1.5 pr-3 font-medium">意图</th>
                        <th className="py-1.5 pr-3 text-right font-medium">引文</th>
                        <th className="py-1.5 pr-3 font-medium">模态</th>
                        <th className="py-1.5 font-medium">时间</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.recent_questions.map((item, index) => (
                        <tr key={`${item.question}-${index}`} className="border-t border-cool-line">
                          <td className="max-w-[360px] py-1.5 pr-3">
                            <div className="truncate text-cool-ink-2" title={item.question}>
                              {item.question || '（空问题）'}
                            </div>
                          </td>
                          <td className="py-1.5 pr-3">
                            <span className="rounded border border-cool-line bg-cool-surface-2 px-1.5 py-0.5 text-[10.5px] text-cool-ink-3">
                              {item.intent_label}
                            </span>
                          </td>
                          <td className={`py-1.5 pr-3 text-right tabular-nums ${item.citations === 0 ? 'text-clay-deep' : 'text-cool-ink-2'}`}>
                            {item.citations}
                          </td>
                          <td className="py-1.5 pr-3 text-[11px] text-cool-ink-3">
                            {[item.has_image && '图片', item.has_audio && '语音'].filter(Boolean).join(' + ') || '文字'}
                          </td>
                          <td className="whitespace-nowrap py-1.5 text-[11px] text-cool-ink-4">
                            {item.created_at ? item.created_at.replace('T', ' ').slice(5, 16) : '—'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>

            <GapNotice items={data.gaps} />
          </div>
        )}
      </StateView>
    </div>
  )
}
