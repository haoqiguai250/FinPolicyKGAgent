import axios from 'axios'

// 创建 Axios 实例
const apiClient = axios.create({
  baseURL: '/api',
  timeout: 300000,  // 5 分钟（后端 KG 查询 + 扰动分析可能需要较长时间）
  headers: {
    'Content-Type': 'application/json',
  },
})

// 请求拦截器
apiClient.interceptors.request.use(
  (config) => config,
  (error) => Promise.reject(error)
)

// 响应拦截器
apiClient.interceptors.response.use(
  (response) => response.data,
  (error) => {
    // 超时处理
    if (error.code === 'ECONNABORTED' || error.message?.includes('timeout')) {
      return Promise.reject(new Error('查询超时（5分钟），请稍后重试或简化查询'))
    }
    
    // 网络错误
    if (error.message === 'Network Error') {
      return Promise.reject(new Error('网络连接失败，请检查后端服务是否启动'))
    }
    
    // HTTP 错误
    if (error.response) {
      const status = error.response.status
      if (status === 500) {
        return Promise.reject(new Error('服务器内部错误，请稍后重试'))
      } else if (status === 404) {
        return Promise.reject(new Error('请求的资源不存在'))
      } else if (status >= 400) {
        return Promise.reject(new Error(`请求错误(${status})，请检查输入`))
      }
    }
    
    console.error('API Error:', error)
    return Promise.reject(error)
  }
)

export default apiClient
