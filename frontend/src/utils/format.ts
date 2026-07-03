// 日期格式化
export function formatDate(date: Date | string | number): string {
  const d = new Date(date)
  const pad = (n: number) => n.toString().padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

// 数字格式化
export function formatNumber(num: number): string {
  if (num >= 10000) {
    return (num / 10000).toFixed(1) + '万'
  }
  return num.toLocaleString()
}

// 百分比格式化
export function formatPercent(value: number, digits = 1): string {
  return (value * 100).toFixed(digits) + '%'
}
