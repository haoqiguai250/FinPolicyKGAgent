// 简单的防抖函数
export function debounce(fn: Function, delay: number = 500): any {
  let timer: number | null = null
  
  const debounced: any = (...args: any[]) => {
    if (timer) clearTimeout(timer)
    timer = setTimeout(() => {
      fn.apply(this, args)
    }, delay) as any
  }
  
  debounced.cancel = () => {
    if (timer) {
      clearTimeout(timer)
      timer = null
    }
  }
  
  return debounced
}

// 简单的内存缓存
class MemoryCache {
  private cache: Map<string, { data: any; timestamp: number }>
  private ttl: number
  
  constructor(ttl: number = 5 * 60 * 1000) {
    this.cache = new Map()
    this.ttl = ttl
  }
  
  private getKey(input: string, params?: any): string {
    return `${input}:${JSON.stringify(params || {})}`
  }
  
  get(input: string, params?: any): any | null {
    const key = this.getKey(input, params)
    const item = this.cache.get(key)
    if (!item) return null
    if (Date.now() - item.timestamp > this.ttl) {
      this.cache.delete(key)
      return null
    }
    console.log('[Cache] Hit:', input)
    return item.data
  }
  
  set(input: string, data: any, params?: any): void {
    const key = this.getKey(input, params)
    this.cache.set(key, { data, timestamp: Date.now() })
    console.log('[Cache] Set:', input)
  }
  
  clear(): void {
    this.cache.clear()
  }
  
  remove(input: string, params?: any): void {
    const key = this.getKey(input, params)
    this.cache.delete(key)
  }
}

export const queryCache = new MemoryCache()
