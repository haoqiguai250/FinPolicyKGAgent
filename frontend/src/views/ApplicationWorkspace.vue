<template>
  <div class="workspace">
    <!-- 演示模式切换（右下角）-->
    <div
      @click="toggleDemo"
      :style="{
        position: 'fixed', bottom: '12px', right: '12px', zIndex: 99999,
        padding: '2px 8px', borderRadius: '4px', fontSize: '11px',
        cursor: 'pointer', fontFamily: 'monospace', userSelect: 'none',
        background: demoMode ? 'rgba(76,175,80,0.15)' : 'transparent',
        color: demoMode ? '#4caf50' : '#ccc',
        border: demoMode ? '1px solid rgba(76,175,80,0.3)' : '1px solid transparent',
      }"
    >{{ demoMode ? '●' : '○' }}</div>
    <!-- ====== 第1层：Hero 区 ====== -->
    <section class="hero-section">
      <div class="hero-bg"></div>
      <div class="hero-content">
        <div class="hero-left">
          <h1 class="hero-title">AI 政策顾问</h1>
          <h2 class="hero-subtitle">助力企业<span class="highlight">精准申报</span></h2>
          <p class="hero-desc">基于企业画像和政策知识库，智能匹配可申报政策，<br/>生成申报建议，提升获批成功率</p>
          <div class="hero-stats" v-if="hasMatched">
            <div class="stat-item">
              <span class="stat-value">{{ matchedPolicies.length }}</span>
              <span class="stat-label">匹配政策</span>
            </div>
            <div class="stat-item">
              <span class="stat-value">{{ totalAmount }}</span>
              <span class="stat-label">预计补贴</span>
            </div>
            <div class="stat-item">
              <span class="stat-value">{{ eligibleCount }}</span>
              <span class="stat-label">可申报</span>
            </div>
          </div>
        </div>
        <!-- IP 角色 — Hero 右侧 -->
        <img src="@/assets/mascot.png" class="hero-mascot" alt="AI 助手" />
      </div>
    </section>

    <!-- ====== 第2层：核心三栏 ====== -->
    <section class="core-section">
      <!-- 卡片1：企业画像 -->
      <div class="core-card profile-card">
        <div class="card-header">
          <div class="header-left">
            <h3>企业画像</h3>
            <span class="card-badge" :class="isProfileComplete ? 'badge-complete' : 'badge-incomplete'">
              {{ isProfileComplete ? '已完善' : '未完善' }}
            </span>
          </div>
          <button class="btn-edit" @click="editProfile">
            <el-icon><Edit /></el-icon>
            <span>编辑</span>
          </button>
        </div>
        <div class="card-body profile-body">
          <!-- 企业名称 + 地区 -->
          <div class="profile-header-block">
            <div class="profile-name" v-if="profileData.name">{{ profileData.name }}</div>
            <div class="profile-region" v-if="profileData.region">
              <el-icon><Location /></el-icon>
              <span>{{ profileData.region }}</span>
            </div>
          </div>
          <!-- 企业类型 -->
          <div class="profile-item">
            <div class="item-left">
              <div class="item-icon icon-purple">
                <el-icon><OfficeBuilding /></el-icon>
              </div>
              <span class="item-label">企业类型</span>
            </div>
            <div class="item-right">
              <template v-if="profileData.company_type">
                <span class="type-tag" v-for="t in (profileData.company_type || '').split(/[,，;；]/)" :key="t">{{ t.trim() }}</span>
              </template>
              <span class="value-empty" v-else>未设置</span>
            </div>
          </div>
          <!-- 所属行业 -->
          <div class="profile-item">
            <div class="item-left">
              <div class="item-icon icon-blue">
                <el-icon><TrendCharts /></el-icon>
              </div>
              <span class="item-label">所属行业</span>
            </div>
            <span class="item-value" :class="{ 'value-empty': !profileData.industry }">
              {{ profileData.industry || '未设置' }}
            </span>
          </div>
          <!-- 员工规模 -->
          <div class="profile-item">
            <div class="item-left">
              <div class="item-icon icon-green">
                <el-icon><User /></el-icon>
              </div>
              <span class="item-label">员工规模</span>
            </div>
            <span class="item-value" :class="{ 'value-empty': !profileData.employees }">
              {{ profileData.employees ? profileData.employees + '人' : '未设置' }}
            </span>
          </div>
          <!-- 年营业收入 -->
          <div class="profile-item">
            <div class="item-left">
              <div class="item-icon icon-orange">
                <el-icon><Money /></el-icon>
              </div>
              <span class="item-label">年营业收入</span>
            </div>
            <span class="item-value" :class="{ 'value-empty': !profileData.annual_revenue }">
              {{ profileData.annual_revenue ? formatMoney(profileData.annual_revenue) : '未设置' }}
            </span>
          </div>
          <!-- 研发投入占比 -->
          <div class="profile-item">
            <div class="item-left">
              <div class="item-icon icon-cyan">
                <el-icon><Timer /></el-icon>
              </div>
              <span class="item-label">研发投入占比</span>
            </div>
            <span class="item-value" :class="{ 'value-empty': !profileData.rd_ratio }">
              {{ profileData.rd_ratio ? profileData.rd_ratio + '%' : '未设置' }}
            </span>
          </div>
        </div>
        <div class="card-footer profile-footer">
          <button class="btn-primary-full" @click="startMatching" :disabled="matching">
            <span v-if="matching" class="btn-loading">
              <span class="spinner"></span> 匹配中...
            </span>
            <span v-else class="btn-content">
              <el-icon><Promotion /></el-icon>
              开始政策匹配
            </span>
          </button>
          <div class="footer-hint">
            <span>完善企业画像，获得更精准推荐</span>
            <el-icon class="hint-icon"><QuestionFilled /></el-icon>
          </div>
        </div>
      </div>

      <!-- 卡片2：AI分析过程 -->
      <div class="core-card analysis-card">
        <div class="card-header">
          <h3>AI 分析过程</h3>
        </div>
        <div class="card-body analysis-body">
          <!-- 匹配前 -->
          <template v-if="!hasMatched && !matching">
            <div class="analysis-empty">
              <div class="empty-illustration">
                <img src="@/assets/9161b78e-14af-4aec-ae66-91846b4e44c2.png" alt="AI 分析" />
              </div>
              <p class="empty-title">尚未开始匹配</p>
              <p class="empty-desc">点击左侧"开始政策匹配"按钮启动 AI 分析</p>
            </div>
            <div class="analysis-steps">
              <div class="step" v-for="(step, i) in analysisSteps" :key="i">
                <span class="step-dot"></span>
                <span class="step-text">{{ step }}</span>
              </div>
            </div>
          </template>

          <!-- 匹配中 -->
          <template v-if="matching">
            <div class="analysis-loading">
              <div class="loading-engine">
                <div class="engine-ring"></div>
                <div class="engine-core"></div>
              </div>
              <p class="loading-text">{{ loadingText }}</p>
            </div>
          </template>

          <!-- 匹配后 -->
          <template v-if="hasMatched">
            <div class="analysis-complete">
              <div class="complete-icon">✓</div>
              <p class="complete-title">分析完成</p>
              <p class="complete-desc">已为您的企业匹配 {{ matchedPolicies.length }} 条可申报政策</p>
            </div>
            <div class="analysis-steps done">
              <div class="step" v-for="(step, i) in analysisSteps" :key="i">
                <span class="step-dot checked"></span>
                <span class="step-text">{{ step }}</span>
              </div>
            </div>
          </template>
        </div>
      </div>

      <!-- 卡片3：机会总览 -->
      <div class="core-card overview-card">
        <div class="card-header">
          <h3>机会总览</h3>
        </div>
        <div class="card-body">
          <div class="overview-grid">
            <div class="ov-item ov-purple">
              <span class="ov-value">{{ hasMatched ? matchedPolicies.length : '--' }}</span>
              <span class="ov-label">匹配政策</span>
            </div>
            <div class="ov-item ov-orange">
              <span class="ov-value">{{ hasMatched ? totalAmount : '--' }}</span>
              <span class="ov-label">预计补贴</span>
            </div>
            <div class="ov-item ov-green">
              <span class="ov-value">{{ hasMatched ? eligibleCount : '--' }}</span>
              <span class="ov-label">优先申报</span>
            </div>
            <div class="ov-item ov-blue">
              <span class="ov-value">{{ hasMatched ? missingCount : '--' }}</span>
              <span class="ov-label">待补资质</span>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- ====== 第3层：推荐政策清单 ====== -->
    <section class="policy-section">
      <div class="section-header">
        <h3>推荐政策清单</h3>
        <span class="btn-clear" v-if="hasMatched" @click="clearResults">清除结果</span>
        <div class="section-filters" v-if="hasMatched">
          <span class="filter-chip">
            <span>全部匹配度</span>
            <el-icon><ArrowDown /></el-icon>
          </span>
          <span class="filter-chip">
            <span>全部类型</span>
            <el-icon><ArrowDown /></el-icon>
          </span>
          <button class="btn-filter">
            <el-icon><Filter /></el-icon>
            <span>筛选</span>
          </button>
        </div>
      </div>

      <!-- 空状态 -->
      <div class="policy-empty" v-if="!hasMatched">
        <img
          src="@/assets/ChatGPT Image 2026年6月6日 16_36_52.png"
          alt="暂无匹配"
          class="empty-illustration"
        />
        <p class="empty-title">暂无匹配结果</p>
        <p class="empty-desc">请先开始政策匹配，AI 将为您推荐合适的申报政策</p>
      </div>

      <!-- 政策表格 -->
      <div class="policy-table" v-else>
        <div class="table-header">
          <span class="col-name">政策名称</span>
          <span class="col-match">匹配度</span>
          <span class="col-amount">预计金额</span>
          <span class="col-dept">申报部门</span>
          <span class="col-deadline">截止时间</span>
          <span class="col-action">操作</span>
        </div>
        <div class="table-body">
          <div
            class="table-row"
            v-for="(item, idx) in policyList"
            :key="idx"
          >
            <span class="col-name">{{ item.name }}</span>
            <span class="col-match">
              <span class="match-bar">
                <span class="match-fill" :style="{ width: item.match + '%' }"></span>
              </span>
              <span class="match-text">{{ item.match }}%</span>
            </span>
            <span class="col-amount">
              <span class="amount-tag" :class="amountClass(item.amount)">{{ item.amount }}</span>
            </span>
            <span class="col-dept">{{ item.department }}</span>
            <span class="col-deadline">{{ item.deadline || '待定' }}</span>
            <span class="col-action">
              <button class="btn-sm" @click="viewPolicy(item)">查看详情</button>
            </span>
          </div>
        </div>
      </div>
    </section>

    <!-- ====== 第4层：四卡行动区 ====== -->
    <section class="action-section">
      <div class="action-card" v-for="card in actionCards" :key="card.title">
        <div class="action-icon" :class="card.color">
          <component :is="card.icon" :size="22" />
        </div>
        <h4>{{ card.title }}</h4>
        <div class="action-content" v-if="hasMatched">
          <p v-for="(line, li) in (card.matched || card.lines || [])" :key="li">{{ line }}</p>
        </div>
        <div class="action-content empty" v-else>
          <p>--</p>
        </div>
      </div>
    </section>

    <!-- ====== 申报工作流弹窗 ====== -->
    <div class="workflow-overlay" v-if="showWorkflow && selectedPolicy" @click.self="showWorkflow = false">
      <div class="workflow-dialog">
        <div class="workflow-header">
          <div class="wf-title-row">
            <h3>{{ selectedPolicy.name }}</h3>
            <div class="wf-tags">
              <span class="wf-meta-tag" :class="selectedPolicy.is_eligible ? 'tag-green' : 'tag-red'">
                {{ selectedPolicy.is_eligible ? '可申报' : '条件不符' }}
              </span>
              <span class="wf-meta-tag tag-purple">匹配度 {{ selectedPolicy.match }}%</span>
              <span v-if="selectedPolicy.amount && selectedPolicy.amount !== '待定'" class="wf-meta-tag tag-orange">{{ selectedPolicy.amount }}</span>
            </div>
          </div>
          <button class="wf-close" @click="showWorkflow = false">&times;</button>
        </div>

      <el-steps :active="activeStep" finish-status="success" align-center simple>
        <el-step title="核验" />
        <el-step title="材料" />
        <el-step title="提交" />
        <el-step title="日历" />
      </el-steps>

      <div class="wf-step-content">
        <!-- ① 核验 -->
        <div v-if="activeStep === 0" class="wf-step">
          <div class="wf-card" v-if="selectedPolicy.eligibility_checks?.length">
            <h4>条件核验</h4>
            <div class="checks-grid">
              <div v-for="(check, ci) in selectedPolicy.eligibility_checks" :key="ci"
                class="check-item" :class="'check-' + check.status">
                <span class="check-icon">
                  {{ check.status === 'pass' ? '✓' : check.status === 'fail' ? '✗' : '?' }}
                </span>
                <span class="check-text">{{ check.condition_text }}</span>
                <span class="check-hint" :class="check.is_hard ? 'hint-hard' : 'hint-soft'">
                  {{ check.is_hard ? '硬条件' : '软条件' }}
                </span>
                <span v-if="check.reason" class="check-reason">{{ check.reason }}</span>
              </div>
            </div>
          </div>
          <div class="wf-card" v-if="selectedPolicy.match_explanation || selectedPolicy.suggestions">
            <h4>AI 分析</h4>
            <div v-if="selectedPolicy.match_explanation" class="ai-text">
              <strong>匹配说明：</strong>{{ selectedPolicy.match_explanation }}
            </div>
            <div v-if="selectedPolicy.suggestions" class="ai-text">
              <strong>申报建议：</strong>{{ selectedPolicy.suggestions }}
            </div>
          </div>
        </div>

        <!-- ② 材料 -->
        <div v-else-if="activeStep === 1" class="wf-step">
          <div class="wf-card">
            <div class="wf-card-header">
              <h4>所需材料</h4>
              <div class="header-actions">
                <button class="btn-sm-primary" v-if="!materialsLoaded[oppIdFromPolicy(selectedPolicy)]"
                  @click="handleGenerateMaterials(oppIdFromPolicy(selectedPolicy))">生成材料清单</button>
                <button class="btn-sm-outline" v-if="!materialsLoaded[oppIdFromPolicy(selectedPolicy)]"
                  @click="loadMaterials(oppIdFromPolicy(selectedPolicy))">加载已有</button>
                <button class="btn-sm-outline" v-else
                  @click="loadMaterials(oppIdFromPolicy(selectedPolicy))">刷新</button>
              </div>
            </div>

            <div v-if="!materialsLoaded[oppIdFromPolicy(selectedPolicy)]" class="materials-tags">
              <span v-for="(mat, mi) in (selectedPolicy.materials || [])" :key="mi" class="mat-tag">📄 {{ mat }}</span>
            </div>

            <div v-else>
              <div class="materials-progress-bar">
                <div class="progress-track">
                  <div class="progress-fill" :style="{ width: (materialsProgress[oppIdFromPolicy(selectedPolicy)] || 0) + '%',
                    background: progressColor(materialsProgress[oppIdFromPolicy(selectedPolicy)] || 0) }"></div>
                </div>
                <span class="progress-text">{{ materialsProgress[oppIdFromPolicy(selectedPolicy)] || 0 }}%</span>
              </div>
              <div v-for="mat in (materialsMap[oppIdFromPolicy(selectedPolicy)] || [])" :key="mat.material_id" class="material-row">
                <label class="mat-check">
                  <input type="checkbox"
                    :checked="mat.status === 'ready' || mat.status === 'submitted' || mat.status === 'waived'"
                    @change="toggleMaterial(mat.material_id, ($event.target as HTMLInputElement).checked ? 'ready' : 'preparing', oppIdFromPolicy(selectedPolicy))" />
                  <span class="mat-name" :class="{ done: mat.status !== 'preparing' }">{{ mat.material_name }}</span>
                </label>
                <span class="mat-status-tag" :class="'status-' + mat.status">{{ matStatusLabel(mat.status) }}</span>
                <span v-if="mat.source !== 'kg'" class="mat-ai-tag">AI生成</span>
              </div>
              <div v-if="(materialsProgress[oppIdFromPolicy(selectedPolicy)] || 0) === 100" class="mat-complete">
                ✅ 所有材料已就绪，可以提交申报！
              </div>
            </div>
          </div>

          <div class="wf-card">
            <div class="wf-card-header">
              <h4>自动生成文档</h4>
              <button class="btn-sm-primary"
                :disabled="generatingDocs[oppIdFromPolicy(selectedPolicy)]"
                @click="handleGenerateDocs(oppIdFromPolicy(selectedPolicy))">
                {{ generatingDocs[oppIdFromPolicy(selectedPolicy)] ? '生成中...' : '生成申报文档' }}
              </button>
            </div>
            <div v-if="(documentsMap[oppIdFromPolicy(selectedPolicy)] || []).length > 0" class="doc-list">
              <div v-for="doc in documentsMap[oppIdFromPolicy(selectedPolicy)]" :key="doc.doc_id" class="doc-row">
                <div class="doc-info">
                  <span class="doc-name">{{ doc.doc_name }}</span>
                  <span class="doc-meta">{{ (doc.doc_type || 'DOCX').toUpperCase() }} · {{ formatFileSize(doc.file_size || 0) }}</span>
                </div>
                <div class="doc-actions">
                  <button class="btn-sm-outline" @click="openDownload(doc.doc_id)">下载</button>
                  <button class="btn-sm-outline danger" @click="handleDeleteDoc(doc.doc_id, oppIdFromPolicy(selectedPolicy))">删除</button>
                </div>
              </div>
            </div>
            <div v-else class="wf-empty">暂无文档，点击上方按钮自动生成</div>
          </div>
        </div>

        <!-- ③ 提交 -->
        <div v-else-if="activeStep === 2" class="wf-step">
          <div class="wf-card">
            <h4>申报信息</h4>
            <div class="info-grid">
              <div v-if="selectedPolicy.deadline" class="info-item">
                <span class="info-label">截止日期</span>
                <span class="info-value">{{ selectedPolicy.deadline }}</span>
              </div>
              <div v-if="selectedPolicy.platform" class="info-item">
                <span class="info-label">申报平台</span>
                <span class="info-value">{{ selectedPolicy.platform }}</span>
              </div>
              <div v-if="selectedPolicy.department && selectedPolicy.department !== '--'" class="info-item">
                <span class="info-label">主管部门</span>
                <span class="info-value">{{ selectedPolicy.department }}</span>
              </div>
              <div v-if="selectedPolicy.amount && selectedPolicy.amount !== '待定'" class="info-item">
                <span class="info-label">资助标准</span>
                <span class="info-value amount">{{ selectedPolicy.amount }}</span>
              </div>
            </div>
          </div>

          <div class="wf-card">
            <h4>申报状态</h4>
            <div class="status-row">
              <span class="status-badge" :class="'badge-' + statusTagType(selectedPolicy.raw?.status || 'discovered')">
                {{ statusLabel(selectedPolicy.raw?.status || 'discovered') }}
              </span>
            </div>

            <div v-if="!selectedPolicy.raw?.status || selectedPolicy.raw.status === 'discovered'" class="submit-area">
              <p class="submit-hint">确认材料就绪后，准备并提交申报包：</p>
              <button class="btn-primary-large" :disabled="preparingPkg"
                @click="handlePrepareSubmission(oppIdFromPolicy(selectedPolicy))">
                {{ preparingPkg ? '准备中...' : '准备申报包' }}
              </button>
            </div>

            <div v-else-if="selectedPolicy.raw.status === 'applying'" class="submit-area">
              <div v-if="submissionPackage && submissionPackage.status === 'ready'" class="package-ready">
                <h4>申报包已就绪</h4>
                <div class="pkg-meta">
                  <span>材料 {{ submissionPackage.materials_checklist?.length || 0 }} 项</span>
                  <span>文档 {{ submissionPackage.documents?.length || 0 }} 份</span>
                </div>
                <button class="btn-success-large" :disabled="confirmingSubmit"
                  @click="handleConfirmSubmission(oppIdFromPolicy(selectedPolicy))">
                  {{ confirmingSubmit ? '提交中...' : '确认提交' }}
                </button>
              </div>
              <div v-else>
                <button class="btn-primary-large" :disabled="preparingPkg"
                  @click="handlePrepareSubmission(oppIdFromPolicy(selectedPolicy))">
                  准备申报包
                </button>
              </div>
            </div>

            <div v-else-if="['submitted', 'approved', 'rejected'].includes(selectedPolicy.raw.status)">
              <div v-if="selectedPolicy.raw.status === 'approved'" class="status-result success">
                🎉 该政策申报已通过！
              </div>
              <div v-else-if="selectedPolicy.raw.status === 'rejected'" class="status-result fail">
                该政策申报未通过。
              </div>
              <div class="tracking-panel">
                <div class="tracking-header">
                  <h4>进度追踪</h4>
                  <button class="btn-sm-text" :disabled="trackingLoading"
                    @click="loadTrackingHistory(oppIdFromPolicy(selectedPolicy))">刷新</button>
                </div>
                <div v-if="trackingHistory.length > 0" class="tracking-timeline">
                  <div v-for="event in trackingHistory" :key="event.event_id" class="timeline-item">
                    <div class="timeline-dot"></div>
                    <div class="timeline-content">
                      <div class="timeline-title">{{ trackingEventLabel(event.event_type) }}</div>
                      <div v-if="event.note" class="timeline-note">{{ event.note }}</div>
                      <div class="timeline-time">{{ event.created_at }}</div>
                    </div>
                  </div>
                </div>
                <div v-else class="timeline-empty">暂无追踪记录</div>
              </div>
            </div>
          </div>

          <div class="wf-card" v-if="selectedPolicy.steps?.length">
            <h4>官方申报流程</h4>
            <el-steps :active="-1" :space="120" align-center>
              <el-step v-for="(step, si) in selectedPolicy.steps" :key="si" :title="step" />
            </el-steps>
          </div>
        </div>

        <!-- ④ 日历 -->
        <div v-else-if="activeStep === 3" class="wf-step">
          <div class="wf-card">
            <h4>申报排期</h4>
            <div class="deadline-card" v-if="selectedPolicy.deadline">
              <span class="deadline-icon">⏰</span>
              <div class="deadline-info">
                <span class="deadline-label">截止日期</span>
                <span class="deadline-value">{{ selectedPolicy.deadline }}</span>
              </div>
            </div>
            <div v-else class="deadline-card no-deadline">
              <span>📅 暂无截止日期信息</span>
            </div>
            <div class="calendar-cta">
              <button class="btn-primary-large" @click="router.push('/calendar')">
                打开完整申报日历 →
              </button>
              <p class="calendar-hint">在日历视图中查看所有政策的截止日期和推荐排期</p>
            </div>
          </div>
        </div>
      </div>

      <!-- 步骤导航 -->
      <div class="wf-nav">
        <button class="btn-nav" @click="prevStep" :disabled="activeStep === 0">&larr; 上一步</button>
        <span class="step-indicator">{{ activeStep + 1 }} / 4</span>
        <button class="btn-nav primary" @click="nextStep" :disabled="activeStep === 3">
          {{ activeStep === 3 ? '已完成' : '下一步 &rarr;' }}
        </button>
      </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, reactive, onMounted } from 'vue'
import { Lightning, List, Document, Service,
  OfficeBuilding, TrendCharts, User, Money, Timer,
  Edit, Promotion, QuestionFilled, Location,
  ArrowDown, Filter,
} from '@element-plus/icons-vue'
import { useAdvisorStore } from '../stores/advisor'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import axios from 'axios'
import {
  fetchMaterials, updateMaterial, generateDocuments, fetchDocuments,
  getDocumentDownloadUrl, deleteDocument,
  prepareSubmission, confirmSubmission, fetchSubmissionPackage,
  fetchTrackingHistory,
} from '../api/advisor'

const advisorStore = useAdvisorStore()
const router = useRouter()

// ── 演示模式 ──
const demoMode = ref(false)
function toggleDemo() {
  demoMode.value = !demoMode.value
  if (demoMode.value) {
    profileData.name = "深圳智创科技有限公司"
    profileData.region = "深圳市南山区"
    profileData.company_type = "民营科技企业"
    profileData.industry = "人工智能 / 信息技术"
    profileData.employees = 380
    profileData.annual_revenue = 12000
    profileData.is_high_tech = true
    profileData.is_sme = true
    profileData.patents = 45
    profileData.rd_ratio = 18
  }
  localStorage.setItem('workspace_demo_mode', demoMode.value ? '1' : '')
}
if (localStorage.getItem('workspace_demo_mode')) {
  demoMode.value = true
}
// Ctrl+Shift+D 快捷键切换演示模式
window.addEventListener('keydown', (e: KeyboardEvent) => {
  if (e.ctrlKey && e.shiftKey && e.key === 'D') {
    e.preventDefault()
    toggleDemo()
  }
})

// ── 状态 ──
const matching = ref(false)
const hasMatched = ref(false)
const showDetail = ref(false)
const showWorkflow = ref(false)
const selectedPolicy = ref<any>(null)
const loadingText = ref('正在分析企业画像...')

// ── 工作流向导状态 ──
const activeStep = ref(0)
const materialsMap = reactive<Record<string, any[]>>({})
const materialsProgress = reactive<Record<string, number>>({})
const materialsLoaded = reactive<Record<string, boolean>>({})
const documentsMap = reactive<Record<string, any[]>>({})
const generatingDocs = reactive<Record<string, boolean>>({})
const submissionPackage = ref<any>(null)
const preparingPkg = ref(false)
const confirmingSubmit = ref(false)
const trackingHistory = ref<any[]>([])
const trackingLoading = ref(false)
const matchedPolicies = ref<any[]>([])
const profileData = reactive<any>({
  name: '',
  region: '',
  company_type: '',
  industry: '',
  employees: '',
  annual_revenue: '',
  rd_ratio: '',
})

// AI 分析步骤
const analysisSteps = ['政策检索', '条件校验', '匹配分析', '生成推荐']

// 画像是否完善
const isProfileComplete = computed(() => {
  return !!(
    profileData.name ||
    profileData.company_type ||
    profileData.industry ||
    profileData.employees ||
    profileData.annual_revenue ||
    profileData.rd_ratio
  )
})

// 编辑企业画像
function editProfile() {
  // 跳转到企业画像页面
  window.location.hash = '#/profile'
}

// 加载企业画像
async function loadProfile() {
  try {
    // 先从 localStorage 取 enterprise_id
    const savedId = localStorage.getItem('profile_enterprise_id') || localStorage.getItem('enterprise_id')

    if (savedId) {
      // 从企业详情接口获取画像（带 /profile 后缀，避免被路由到列表接口）
      try {
        const res = await axios.get(`/api/enterprises/${savedId}/profile`)
        // 响应结构：{ enterprise_id, name, profile: {...} }
        if (res.data) {
          if (res.data.name) profileData.name = res.data.name
          if (res.data.profile) Object.assign(profileData, res.data.profile)
        }
      } catch (e) {
        console.warn('获取企业画像失败，尝试 push profile:', e)
      }
    }

    // 兜底：从推送画像接口获取
    const params: Record<string, string> = {}
    if (savedId) params.enterprise_id = savedId
    const profileRes = await axios.get('/api/push/profile', { params })
    // push/profile 直接返回画像 dict，非嵌套
    if (profileRes.data) {
      if (profileRes.data.region) profileData.region = profileRes.data.region
      if (profileRes.data.company_type) profileData.company_type = profileRes.data.company_type
      if (profileRes.data.industry) profileData.industry = profileRes.data.industry
      if (profileRes.data.employees) profileData.employees = profileRes.data.employees
      if (profileRes.data.annual_revenue) profileData.annual_revenue = profileRes.data.annual_revenue
      if (profileRes.data.rd_ratio) profileData.rd_ratio = profileRes.data.rd_ratio
      if (profileRes.data.name) profileData.name = profileRes.data.name || ''
    }
  } catch (e) {
    console.error('加载企业画像异常:', e)
  }
}

// 开始匹配
async function startMatching() {
  matching.value = true
  hasMatched.value = false
  loadingText.value = '正在分析企业画像...'

  const loadingSteps = [
    { delay: 2500, text: '正在检索相关政策...' },
    { delay: 3000, text: '正在校验申报条件...' },
    { delay: 3000, text: '正在生成匹配结果...' },
  ]

  let stepIdx = 0
  function advanceLoading() {
    if (stepIdx < loadingSteps.length && matching.value) {
      const step = loadingSteps[stepIdx]
      loadingText.value = step.text
      stepIdx++
      setTimeout(advanceLoading, step.delay)
    }
  }
  advanceLoading()

  try {
    // 🎬 演示模式：直接返回静态数据
    if (demoMode.value) {
      // 注入演示企业画像
      profileData.name = "深圳智创科技有限公司"
      profileData.region = "深圳市南山区"
      profileData.company_type = "民营科技企业"
      profileData.industry = "人工智能 / 信息技术"
      profileData.employees = 380
      profileData.annual_revenue = 12000
      profileData.is_high_tech = true
      profileData.is_sme = true
      profileData.patents = 45
      profileData.rd_ratio = 18

      await new Promise(r => setTimeout(r, 10000))
      const demoPolicies = [
        { name: "深圳市研发投入补助计划项目管理办法", match: 95, amount: "20 ~ 300 万", department: "深圳市科技创新局", deadline: "2031-02-25", match_explanation: "企业成立满两个会计年度，近两年均享受研发加计扣除；上年研发费用 2160 万，增量远超 200 万门槛；诚信记录良好；政策有效期五年（至2031年）", suggestions: ["建议优先申报", "准备近两年企业所得税年度纳税申报表", "研发费用数据需与税务加计扣除一致"], eligibility_checks: [{condition_text:"深圳市注册的独立法人企业", status:"pass", is_hard:true, reason:"南山区注册，具有独立法人资格"}, {condition_text:"成立满两个会计年度", status:"unknown", is_hard:true, reason:"画像未填写成立日期，需确认"}, {condition_text:"近两年均申报研发费用加计扣除", status:"unknown", is_hard:false, reason:"需提供近两年企业所得税申报表"}, {condition_text:"上年度研发费用增量 ≥ 200 万元", status:"pass", is_hard:true, reason:"上年研发费 2160 万，实际增量充足"}, {condition_text:"诚信记录良好，无限制申请情形", status:"pass", is_hard:true, reason:"无失信记录，无项目超期未验收"}, {condition_text:"建立研发准备金制度（事前资助）", status:"unknown", is_hard:false, reason:"事前资助需另行申报，门槛更高"}, {condition_text:"规上工业企业/科技服务业企业", status:"pass", is_hard:false, reason:"年营收 1.2 亿，属规上企业"}, {condition_text:"研发费用核算规范（专账管理）", status:"unknown", is_hard:false, reason:"需提供研发费用辅助账"}], amount_detail:"分档梯度资助：根据研发费用增长幅度分档，最低不少于 20 万，最高不超过 300 万。注册成立不足两年企业按最近一个会计年度研发费用参照上述档位资助。事前研发费用资助（建立研发准备金制度）另行制定。另鼓励各区按一定比例给予配套资助。", application_platform:"深圳市科技业务管理系统", contact:"市科创局 0755-88123456", materials:["近两年企业所得税年度纳税申报表", "研发费用辅助账", "营业执照副本", "诚信承诺书"], steps:["市科创局发布申请指南", "通过深圳市科技业务管理系统填报申请", "市科创局形式审查 + 抽查核实", "确定拟资助项目并社会公示 5 个工作日", "公示无异议后下达资助计划拨付资金"] },
        { name: "坪山区数字经济高质量发展资金支持措施", match: 88, amount: "最高 100 万", department: "坪山区工业和信息化局", deadline: "", match_explanation: "企业属数字经济/AI 产业，符合坪山区重点发展方向；已纳入规上企业库", suggestions: ["确认是否已在坪山区有实际经营场所", "准备数字化改造方案及投入证明"], eligibility_checks: [{condition_text:"注册地在坪山区", status:"fail", is_hard:true, reason:"企业注册于南山区，非坪山区"}, {condition_text:"纳入规上企业库", status:"pass", is_hard:true, reason:"年营收 1.2 亿，已纳入统计"}, {condition_text:"属数字经济产业", status:"pass", is_hard:false, reason:"AI 属数字经济技术方向"}, {condition_text:"有数字化改造项目", status:"unknown", is_hard:false, reason:"需提供改造方案及预算"}, {condition_text:"上年度营收 ≥ 2000 万", status:"pass", is_hard:true, reason:"年营收 1.2 亿"}, {condition_text:"软件产品/服务已上架应用", status:"unknown", is_hard:false, reason:"画像未填写软件产品信息"}], amount_detail:"单个企业年度最高资助 100 万元；安全服务机构年度最高 100 万元奖励。", application_platform:"坪山区企业服务平台", contact:"坪山区工信局 0755-28331234" },
        { name: "坪山区金融扶持政策", match: 72, amount: "最高 1000 万", department: "坪山区金融工作局", deadline: "", match_explanation: "企业属于金融机构/新兴金融服务机构范畴，可申请落户奖励、办公用房补贴及融资配套资助", suggestions: ["如计划在坪山区设立分支机构，可叠加落户+用房奖励", "确认实缴注册资本是否达标"], eligibility_checks: [{condition_text:"注册地在坪山区", status:"fail", is_hard:true, reason:"南山区注册，需迁址或新设坪山主体"}, {condition_text:"实缴注册资本 ≥ 1 亿", status:"unknown", is_hard:true, reason:"画像未填写注册资本"}, {condition_text:"从业人员 ≥ 20 人", status:"pass", is_hard:false, reason:"现有 380 人"}, {condition_text:"合同期三年以上", status:"unknown", is_hard:false, reason:"无坪山区物业租赁合同"}, {condition_text:"第一个会计年度营收 ≥ 1000 万", status:"pass", is_hard:false, reason:"已超 1.2 亿"}, {condition_text:"属金融机构/新兴金融服务机构", status:"fail", is_hard:false, reason:"企业主营 AI 研发，非金融机构"}], amount_detail:"金融机构总部落户奖励最高 1000 万元；一级分支机构最高 200 万元；新购置办公用房每平方米 1000 元最高 100 万元；融资配套活动资助 50% 单次最高 50 万元。", application_platform:"坪山区金融工作局", contact:"坪山区金融局 0755-28339988" },
        { name: "坪山区支持实体经济发展若干措施", match: 65, amount: "待定", department: "坪山区人民政府", deadline: "2020-12-31", match_explanation: "政策覆盖范围广，包含产值奖励、技术改造资助、总部落户等多项措施，但企业注册地不在坪山区", suggestions: ["产值增长奖励条件可满足，但需在坪山区注册", "考虑在坪山设立生产基地或子公司"], eligibility_checks: [{condition_text:"注册地、经营地、纳税地均在坪山区", status:"fail", is_hard:true, reason:"企业注册于南山区，三地均不在坪山"}, {condition_text:"独立法人资格", status:"pass", is_hard:true, reason:"具有独立法人资格"}, {condition_text:"产值 ≥ 1 亿元", status:"pass", is_hard:false, reason:"年营收 1.2 亿"}, {condition_text:"当年产值同比增长", status:"unknown", is_hard:false, reason:"需提供去年产值对比数据"}, {condition_text:"获中国/省/市质量奖", status:"fail", is_hard:false, reason:"未见相关获奖记录"}, {condition_text:"属世界/中国 500 强", status:"fail", is_hard:false, reason:"非 500 强企业"}], amount_detail:"产值增长奖励：按增长部分 0.5%-1% 最高 5000 万；技术改造资助最高 5000 万；上市企业总部迁入奖励最高 500 万。", application_platform:"坪山区公共资源交易平台", contact:"坪山区政府 0755-28451234" },
        { name: "优质中小企业梯度培育管理办法", match: 80, amount: "待定", department: "工业和信息化部", deadline: "", match_explanation: "企业已获专精特新中小企业认定，符合梯度培育体系；可逐步冲刺国家级小巨人", suggestions: ["准备近两年市场占有率证明（第三方）", "完善主导产品收入结构数据"], eligibility_checks: [{condition_text:"符合中小企业划型标准", status:"pass", is_hard:true, reason:"380 人/1.2 亿，属中型企业"}, {condition_text:"已认定专精特新中小企业", status:"pass", is_hard:true, reason:"已获认定"}, {condition_text:"从事特定细分市场 ≥ 3 年", status:"unknown", is_hard:true, reason:"画像未填写成立日期及细分市场年限"}, {condition_text:"未被列入经营异常或失信名单", status:"pass", is_hard:true, reason:"信用记录正常"}, {condition_text:"产品不属于禁止/限制/淘汰类", status:"pass", is_hard:true, reason:"AI 产品属鼓励类"}, {condition_text:"已有上市计划或已在辅导", status:"unknown", is_hard:false, reason:"画像未填写资本规划"}], amount_detail:"中央财政对入选专精特新小巨人企业给予 200 万元一次性奖补，深圳市按 1:1 配套。", application_platform:"优质中小企业梯度培育平台", contact:"市中小企业服务局 0755-88345678" },
        { name: "工业互联网和人工智能融合赋能行动方案", match: 85, amount: "待定", department: "工业和信息化部", deadline: "", match_explanation: "企业主营 AI 技术，与方案目标一致；属电子信息重点行业，可参与工业模型训练、质量检测等应用场景", suggestions: ["积极对接工业互联网平台企业", "准备 AI 在工业场景的解决方案"], eligibility_checks: [{condition_text:"属于电子信息等重点行业", status:"pass", is_hard:true, reason:"AI/信息技术属电子信息"}, {condition_text:"具备工业数据或模型训练能力", status:"pass", is_hard:false, reason:"AI 研发企业具备相关能力"}, {condition_text:"为工业企业/工业互联网平台企业", status:"unknown", is_hard:false, reason:"需确认是否有工业客户合作"}, {condition_text:"拥有自主 AI 模型或算法", status:"pass", is_hard:false, reason:"自主研发 AI 产品"}, {condition_text:"参与过工业数据可信流通空间", status:"fail", is_hard:false, reason:"未见相关参与记录"}, {condition_text:"已获得工业互联网相关资质", status:"fail", is_hard:false, reason:"未见工业互联网平台认证"}], amount_detail:"方案为政策引导性文件，具体资金由后续专项申报确定。", application_platform:"工信部项目申报系统", contact:"市工信局 0755-88234567" },
        { name: "政府采购促进中小企业发展管理办法", match: 78, amount: "报价扣除 6%-10%", department: "财政部", deadline: "", match_explanation: "企业符合中小微企业标准，参与政府采购时可享受价格评审优惠和份额预留", suggestions: ["注册政府采购供应商库", "准备《中小企业声明函》"], eligibility_checks: [{condition_text:"符合中小企业划型标准", status:"pass", is_hard:true, reason:"380 人/1.2 亿，中型企业"}, {condition_text:"货物由中小企业制造", status:"pass", is_hard:false, reason:"自研 AI 产品"}, {condition_text:"出具《中小企业声明函》", status:"unknown", is_hard:true, reason:"需申报时出具"}, {condition_text:"非对外援助/资格资质特殊项目", status:"pass", is_hard:false, reason:"属常规采购范围"}, {condition_text:"联合体小微份额 ≥ 30%", status:"unknown", is_hard:false, reason:"如联合投标需评估"}, {condition_text:"非大型企业控股子公司", status:"pass", is_hard:true, reason:"独立民营企业"}], amount_detail:"小微企业报价给予 6%-10% 扣除（工程项目 3%-5%）；预留份额不低于 30%。", application_platform:"中国政府采购网", contact:"市财政局采购办 0755-88123456" },
        { name: "坪山区促进社区集体经济产业转型发展实施细则", match: 55, amount: "待定", department: "坪山区国有资产监督管理局", deadline: "", match_explanation: "政策面向社区股份合作公司和物业改造项目，企业若在坪山租赁或改造厂房可适用", suggestions: ["如在坪山区租赁产业用房，可申请装修改造资助", "改造后为办公/研发用途的资助标准更高"], eligibility_checks: [{condition_text:"注册地在坪山区", status:"fail", is_hard:true, reason:"企业注册于南山区"}, {condition_text:"签订物业租赁合同三年以上", status:"unknown", is_hard:true, reason:"无坪山区物业租赁记录"}, {condition_text:"企业主营业务属鼓励类产业", status:"pass", is_hard:false, reason:"AI 属鼓励类"}, {condition_text:"社区股份合作公司/区属国企", status:"fail", is_hard:false, reason:"民营企业，非社区股份公司"}, {condition_text:"装修改造项目已立项", status:"unknown", is_hard:false, reason:"无坪山区物业改造项目"}], amount_detail:"办公/研发用途改造最高 3500 元/m²；生产用途最高 2000 元/m²；宿舍/饭堂最高 3000 元/m²；绿化改造最高 100 元/m²。", application_platform:"坪山区公共资源交易平台", contact:"坪山区国资局 0755-28331000" },
        { name: "服务业经营主体贷款贴息政策", match: 70, amount: "待定", department: "国家发展改革委/财政部", deadline: "", match_explanation: "企业属数字领域经营主体，符合服务业贷款贴息支持方向", suggestions: ["确认当年新增贷款记录", "准备贷款用途为数字领域经营的证明材料"], eligibility_checks: [{condition_text:"属于服务业经营主体", status:"pass", is_hard:true, reason:"AI 研发属数字服务领域"}, {condition_text:"当年有新增贷款", status:"unknown", is_hard:false, reason:"需提供银行贷款合同"}, {condition_text:"贷款用于经营周转", status:"unknown", is_hard:false, reason:"需提供资金用途说明"}, {condition_text:"非限制性行业", status:"pass", is_hard:true, reason:"信息技术不属于限制类"}, {condition_text:"企业信用良好", status:"pass", is_hard:true, reason:"无失信记录"}, {condition_text:"非民办非企业法人养老机构", status:"pass", is_hard:false, reason:"民营科技企业"}], amount_detail:"按实际贷款利息的一定比例贴息，具体标准由地方实施细则确定。", application_platform:"深i企/全国信易贷平台", contact:"市发改委 0755-88101234" },
        { name: "推动工业互联网平台高质量发展行动方案", match: 76, amount: "待定", department: "工业和信息化部", deadline: "", match_explanation: "企业具备模型开发能力，可参与工业互联网平台生态建设；方案鼓励民营企业参与", suggestions: ["开发面向制造业的 AI 解决方案", "与工业互联网平台企业建立合作"], eligibility_checks: [{condition_text:"属于民营/中小企业", status:"pass", is_hard:false, reason:"民营科技企业"}, {condition_text:"具备模型开发能力", status:"pass", is_hard:false, reason:"AI 研发企业"}, {condition_text:"属制造业相关领域", status:"unknown", is_hard:false, reason:"需确认工业客户合作情况"}, {condition_text:"已接入工业互联网平台", status:"fail", is_hard:false, reason:"未见平台接入记录"}, {condition_text:"有垂直行业解决方案", status:"pass", is_hard:false, reason:"已有 AI 行业应用产品"}, {condition_text:"通过工业互联网安全分类分级", status:"fail", is_hard:true, reason:"未进行安全分类分级认证"}], amount_detail:"引导性政策文件，具体资金由工业互联网专项和平台企业合作渠道落实。", application_platform:"工信部工业互联网专项", contact:"市工信局 0755-88234567" },
        { name: "国家产业技术工程化中心管理办法", match: 68, amount: "待定", department: "国家发展改革委", deadline: "", match_explanation: "企业拥有自主知识产权和研发能力，可申报产业技术工程化中心，促进成果产业化", suggestions: ["梳理待工程化开发的重大科技成果", "完善成果转化激励制度"], eligibility_checks: [{condition_text:"拥有自主知识产权", status:"pass", is_hard:true, reason:"45 项有效专利"}, {condition_text:"具有工程化研究验证能力", status:"unknown", is_hard:false, reason:"需提供实验室/中试条件说明"}, {condition_text:"具有成果转化激励制度", status:"unknown", is_hard:false, reason:"画像未填写管理制度情况"}, {condition_text:"未列入严重失信名单", status:"pass", is_hard:true, reason:"信用记录正常"}, {condition_text:"符合发改委建设领域要求", status:"unknown", is_hard:true, reason:"需对照当期申报指南"}, {condition_text:"拥有行业领先的重大科技成果", status:"pass", is_hard:false, reason:"AI 技术属前沿领域"}], amount_detail:"中央预算内投资或专项基金支持，具体额度按项目评审确定。", application_platform:"国家发展改革委项目申报系统", contact:"市发改委 0755-88101234" },
        { name: "深圳市宝安区市场监管局全链条服务护航企业高质量发展", match: 62, amount: "待定", department: "深圳市市场监督管理局宝安监管局", deadline: "", match_explanation: "宝安区面向各类经营主体（含小微企业）的全链条服务，含出海支持、质量提升等", suggestions: ["如有宝安区业务可了解分所/分公司设立政策", "关注名特优新个体工商户转型企业政策"], eligibility_checks: [{condition_text:"注册地在宝安区", status:"fail", is_hard:true, reason:"企业注册于南山区，非宝安"}, {condition_text:"属小微企业/个体工商户", status:"pass", is_hard:false, reason:"中型企业，可参考"}, {condition_text:"有出海需求", status:"unknown", is_hard:false, reason:"画像未填写国际化业务情况"}, {condition_text:"属外向型优势产业集群", status:"unknown", is_hard:false, reason:"AI 行业是否纳入需确认"}, {condition_text:"制造业企业", status:"fail", is_hard:false, reason:"主营 AI 研发，非制造业"}], amount_detail:"服务类政策，具体资金标准由各专项计划确定。", application_platform:"宝安区企业服务平台", contact:"宝安市场监管局 0755-27831234" },
        { name: "推动物联网产业创新发展行动方案（2026-2028年）", match: 71, amount: "待定", department: "工业和信息化部等九部门", deadline: "", match_explanation: "方案覆盖信息技术、工业、交通等多个行业，企业可切入物联网+AI 融合方向", suggestions: ["探索物联网+AI 产品方案", "关注异构网络融合等关键技术攻关机会"], eligibility_checks: [{condition_text:"属信息技术/工业等行业", status:"pass", is_hard:false, reason:"AI/信息技术符合"}, {condition_text:"有物联网相关产品或研发计划", status:"unknown", is_hard:false, reason:"画像未提及物联网方向"}, {condition_text:"具备跨领域技术融合能力", status:"pass", is_hard:false, reason:"AI 具有通用融合能力"}, {condition_text:"参与过国家级科技项目", status:"unknown", is_hard:false, reason:"画像未填写项目参与记录"}, {condition_text:"拥有核心自主技术", status:"pass", is_hard:true, reason:"45 项专利"}], amount_detail:"引导性文件，具体资金通过工信部专项和地方政府配套落实。", application_platform:"工信部科技司项目申报", contact:"市工信局 0755-88234567" },
        { name: "中央预算内投资计划管理办法", match: 58, amount: "待定", department: "国家发展改革委", deadline: "", match_explanation: "高新技术项目可争取中央预算内投资，需纳入国家重大建设项目库", suggestions: ["将重点研发项目纳入国家重大建设项目库", "准备项目可行性研究报告"], eligibility_checks: [{condition_text:"属国家重点支持领域", status:"pass", is_hard:true, reason:"AI/新一代信息技术属重点方向"}, {condition_text:"已纳入国家重大建设项目库", status:"fail", is_hard:true, reason:"未见项目入库记录"}, {condition_text:"项目完成可行性研究", status:"unknown", is_hard:false, reason:"需提交可研报告"}, {condition_text:"落实地方配套资金", status:"unknown", is_hard:false, reason:"需与地方发改部门确认配套能力"}, {condition_text:"企业资信良好", status:"pass", is_hard:true, reason:"无失信记录"}, {condition_text:"符合年度投资计划方向", status:"unknown", is_hard:true, reason:"需对照当年申报指南"}], amount_detail:"按项目评审确定中央预算内投资额度，需地方配套。", application_platform:"投资项目在线审批监管平台（国家重大建设项目库）", contact:"市发改委 0755-88101234" },
        { name: "关于十五五期间支持科技创新进口税收优惠政策管理办法", match: 66, amount: "待定", department: "科技部/海关总署", deadline: "", match_explanation: "高新技术企业进口研发设备可享受关税减免，企业属外资/民营科技企业均适用", suggestions: ["梳理进口研发设备清单", "确认设备是否在免税目录内"], eligibility_checks: [{condition_text:"属科技创新主体", status:"pass", is_hard:true, reason:"高新技术企业"}, {condition_text:"进口设备用于研发", status:"unknown", is_hard:false, reason:"需确认是否有进口设备采购计划"}, {condition_text:"设备属免税目录范围", status:"unknown", is_hard:true, reason:"需对照海关免税目录"}, {condition_text:"未被列入信用异常名单", status:"pass", is_hard:true, reason:"信用正常"}, {condition_text:"已进行事前研发费用资助登记", status:"unknown", is_hard:false, reason:"需确认科技部门登记状态"}, {condition_text:"外资/内资企业均适用", status:"pass", is_hard:false, reason:"民营科技企业"}], amount_detail:"免征关税和进口环节增值税，具体金额视进口设备货值而定。", application_platform:"科技部+海关总署联合审批系统", contact:"市科创局 0755-88123456" },
      ]
      matchedPolicies.value = demoPolicies as any
      hasMatched.value = true
      matching.value = false
      return
      return
    }

    // 构建查询
    const parts: string[] = []
    if (profileData.region) parts.push(profileData.region)
    if (profileData.industry) parts.push(profileData.industry)
    if (profileData.company_type) parts.push(profileData.company_type)
    const query = parts.length > 0
      ? `询问${parts.join('')}企业的补贴政策`
      : '询问深圳市科技企业的补贴政策'

    // 调用工作台专用接口（自动加载企业画像 + 跳过 RAG 长文生成）
    const enterpriseId = localStorage.getItem('profile_enterprise_id') || localStorage.getItem('enterprise_id') || ''
    const params = enterpriseId ? `?enterprise_id=${enterpriseId}` : ''
    const res = await axios.post(`/api/advise/opportunities${params}`, { query, fast_mode: true })

    if (res.data) {
      const result = res.data
      // 使用 opportunities 结构化数据
      const policies: any[] = []
      const seenNames = new Set<string>()

      for (const opp of (result.opportunities || [])) {
        const name = opp.policy_name
        if (!seenNames.has(name)) {
          seenNames.add(name)
          // 从 eligibility_checks 中提取匹配度
          const totalChecks = (opp.hard_pass_count || 0) + (opp.hard_fail_count || 0)
            + (opp.soft_pass_count || 0) + (opp.unknown_count || 0)
          const passCount = (opp.hard_pass_count || 0) + (opp.soft_pass_count || 0)
          const matchPct = totalChecks > 0 ? Math.floor((passCount / totalChecks) * 100) : 70

          policies.push({
            name,
            match: matchPct,
            amount: opp.estimated_amount || '待定',
            department: opp.source_department || '--',
            deadline: opp.deadline || '',
            status: opp.is_eligible ? '可申报' : '条件不符',
            is_eligible: opp.is_eligible,
            eligibility_checks: opp.eligibility_checks || [],
            materials: opp.required_materials || [],
            steps: opp.application_steps || [],
            match_explanation: opp.match_explanation || '',
            suggestions: opp.suggestions || '',
            platform: opp.platform_name || '',
            raw: opp,
          })
        }
      }

      matchedPolicies.value = policies
      hasMatched.value = true

      // 保存到 store
      advisorStore.currentResult = result as any
      advisorStore.addHistory(query, result)
      
      // 💾 保存到 localStorage，页面切换后自动恢复
      try {
        localStorage.setItem('workspace_matched_' + enterpriseId, JSON.stringify({
          policies,
          profileData: { ...profileData },
          timestamp: Date.now(),
        }))
      } catch { /* ignore */ }
    }
  } catch (err) {
    console.error('匹配失败:', err)
  } finally {
    matching.value = false
  }
}

// 格式化金额
function formatMoney(val: any): string {
  if (!val) return '--'
  const n = Number(val)
  if (n >= 10000) return (n / 10000).toFixed(0) + '亿'
  if (n >= 1000) return (n / 1000).toFixed(0) + '千万'
  return n + '万'
}

// 计算统计 — 有金额的排上面，待定的排下面
const policyList = computed(() => {
  const list = [...matchedPolicies.value]
  list.sort((a: any, b: any) => {
    const aHasAmount = a.amount && a.amount !== '待定'
    const bHasAmount = b.amount && b.amount !== '待定'
    if (aHasAmount && !bHasAmount) return -1
    if (!aHasAmount && bHasAmount) return 1
    // 都有金额时按金额从高到低排
    const aNum = parseInt(String(a.amount).replace(/[^0-9]/g, '')) || 0
    const bNum = parseInt(String(b.amount).replace(/[^0-9]/g, '')) || 0
    return bNum - aNum
  })
  return list
})
const totalAmount = computed(() => {
  if (!hasMatched.value) return '--'
  const amounts = policyList.value
    .map((p: any) => {
      const m = String(p.amount).match(/(\d+)/)
      return m ? parseInt(m[1]) : 0
    })
    .filter((n: number) => n > 0)
  if (amounts.length === 0) return '待定'
  const min = Math.min(...amounts) * 0.7
  const max = Math.max(...amounts) * 1.2
  return `${Math.round(min)}-${Math.round(max)}万`
})
const eligibleCount = computed(() =>
  hasMatched.value ? policyList.value.filter((p: any) => p.status === '可申报').length : 0
)
const missingCount = computed(() =>
  hasMatched.value ? policyList.value.filter((p: any) => p.status !== '可申报').length : 0
)

// 查看政策详情 — 展开工作流
function viewPolicy(item: any) {
  selectedPolicy.value = item
  activeStep.value = 0
  showDetail.value = false
  showWorkflow.value = true
  // 自动加载材料 + 文档
  const oppId = oppIdFromPolicy(item)
  if (oppId) {
    loadMaterials(oppId)
    loadDocuments(oppId)
    loadSubmissionPackage(oppId)
    loadTrackingHistory(oppId)
  }
}

function closeWorkflow() {
  showWorkflow.value = false
  selectedPolicy.value = null
}

function oppIdFromPolicy(item: any): string {
  return item.raw?.opportunity_id || item.opportunity_id || ''
}

// ── 向导导航 ──
function nextStep() { if (activeStep.value < 3) activeStep.value++ }
function prevStep() { if (activeStep.value > 0) activeStep.value-- }

// ── 状态机 ──
function statusLabel(status: string): string {
  const labels: Record<string, string> = {
    discovered: '已发现', applying: '申报中', submitted: '已提交',
    approved: '已通过', rejected: '未通过',
  }
  return labels[status] || status
}
function statusTagType(status: string): string {
  const types: Record<string, string> = {
    discovered: 'info', applying: 'warning', submitted: '',
    approved: 'success', rejected: 'danger',
  }
  return types[status] || 'info'
}

// ── 材料交互 ──
async function loadMaterials(opportunityId: string) {
  // 演示模式：展示静态材料清单
  if (demoMode.value) {
    const policy = matchedPolicies.value.find((p: any) => oppIdFromPolicy(p) === opportunityId)
      || matchedPolicies.value.find((p: any) => (p.name || '').replace(/[^\\u4e00-\\u9fa5]/g, '') === opportunityId)
    const rawMats: string[] = policy?.materials || []
    const mats = rawMats.map((name: string, i: number) => ({
      material_id: 'demo_mat_' + i,
      opportunity_id: opportunityId,
      material_name: name,
      status: i === 0 ? 'ready' : 'preparing',
      notes: '',
      source: name.includes('AI') || name.includes('生成') ? 'llm' : ('kg' as string),
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    }))
    materialsMap[opportunityId] = mats
    materialsProgress[opportunityId] = mats.length > 0 ? Math.round(mats.filter((m: any) => m.status === 'ready').length / mats.length * 100) : 0
    materialsLoaded[opportunityId] = true
    return
  }
  try {
    const result = await fetchMaterials(opportunityId)
    materialsMap[opportunityId] = result.materials
    materialsProgress[opportunityId] = result.progress?.progress_pct || 0
    materialsLoaded[opportunityId] = true
  } catch { /* noop */ }
}

async function toggleMaterial(materialId: string, newStatus: string, opportunityId: string) {
  try {
    await updateMaterial(materialId, newStatus)
    await loadMaterials(opportunityId)
  } catch { /* noop */ }
}

function matStatusType(status: string): string {
  const types: Record<string, string> = {
    preparing: 'info', ready: 'success', submitted: '', waived: 'warning',
  }
  return types[status] || 'info'
}

function matStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    preparing: '准备中', ready: '已就绪', submitted: '已提交', waived: '豁免',
  }
  return labels[status] || status
}

function progressColor(pct: number): string {
  if (pct >= 100) return '#059669'
  if (pct >= 50) return '#d97706'
  return '#dc2626'
}

// ── 文档生成 ──
async function handleGenerateMaterials(opportunityId: string) {
  // 演示模式：秒出模拟材料
  if (demoMode.value) {
    await new Promise(r => setTimeout(r, 800))
    await loadMaterials(opportunityId)
    ElMessage.success('材料清单已生成')
    return
  }
  generatingDocs[opportunityId] = true
  try {
    await generateMaterials(opportunityId)
    await loadMaterials(opportunityId)
    ElMessage.success('材料清单已生成')
  } catch {
    ElMessage.error('材料生成失败')
  } finally {
    generatingDocs[opportunityId] = false
  }
}

async function handleGenerateDocs(opportunityId: string) {
  // 演示模式：调用后端 python-docx 生成 Word 文件并直接下载
  if (demoMode.value) {
    generatingDocs[opportunityId] = true
    try {
      const policy: any = selectedPolicy.value || {}
      const body: any = {
        policy_name: policy.name || '',
        doc_type: 'application',  // 先只生成申报书（承诺函需要后端策略调整）
        materials: policy.materials || [],
        steps: policy.steps || [],
        amount_detail: policy.amount_detail || policy.amount || '',
        deadline: policy.deadline || '',
        department: policy.department || '',
        enterprise_name: profileData.name || '',
        enterprise_region: profileData.region || '',
        enterprise_type: profileData.company_type || '',
        enterprise_industry: profileData.industry || '',
        enterprise_employees: String(profileData.employees || ''),
        enterprise_revenue: String(profileData.annual_revenue || ''),
      }
      const res = await axios.post('/api/demo/documents/generate', body, { responseType: 'blob' })
      const blob = res.data as Blob
      const url = URL.createObjectURL(blob)
      const docName = (policy.name || '政策申报').slice(0, 15) + '申报书.docx'
      documentsMap[opportunityId] = [{
        doc_id: 'demo_doc_application', doc_name: docName,
        doc_type: 'docx', file_size: blob.size, created_at: new Date().toISOString(),
        _blobUrl: url,
      }]
      ElMessage.success('申报书已生成')
    } catch {
      ElMessage.error('文档生成失败，请检查后端服务')
    } finally {
      generatingDocs[opportunityId] = false
    }
    return
  }
  generatingDocs[opportunityId] = true
  try {
    await generateDocuments(opportunityId)
    await loadDocuments(opportunityId)
    ElMessage.success('文档生成完成')
  } catch {
    ElMessage.error('文档生成失败')
  } finally {
    generatingDocs[opportunityId] = false
  }
}

async function loadDocuments(opportunityId: string) {
  try {
    const result = await fetchDocuments(opportunityId)
    documentsMap[opportunityId] = result.documents || []
  } catch {
    documentsMap[opportunityId] = []
  }
}

async function handleDeleteDoc(docId: string, opportunityId: string) {
  if (demoMode.value) {
    documentsMap[opportunityId] = (documentsMap[opportunityId] || []).filter((d: any) => d.doc_id !== docId)
    ElMessage.success('文档已删除')
    return
  }
  try {
    await deleteDocument(docId)
    await loadDocuments(opportunityId)
    ElMessage.success('文档已删除')
  } catch {
    ElMessage.error('删除失败')
  }
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

function openDownload(docId: string) {
  // 演示模式：blob URL 下载
  if (demoMode.value) {
    const docs = documentsMap[oppIdFromPolicy(selectedPolicy.value)] || []
    const doc = docs.find((d: any) => d.doc_id === docId)
    if (doc?._blobUrl) {
      const a = document.createElement('a')
      a.href = doc._blobUrl; a.download = doc.doc_name; a.click()
      return
    }
  }
  window.open(getDocumentDownloadUrl(docId), '_blank')
}

// ── 申报提交 ──
async function loadSubmissionPackage(opportunityId: string) {
  try { submissionPackage.value = await fetchSubmissionPackage(opportunityId) }
  catch { submissionPackage.value = null }
}

async function handlePrepareSubmission(opportunityId: string) {
  preparingPkg.value = true
  try {
    submissionPackage.value = await prepareSubmission(opportunityId)
    ElMessage.success('申报包已准备完成')
  } catch {
    ElMessage.error('准备申报包失败')
  } finally { preparingPkg.value = false }
}

async function handleConfirmSubmission(opportunityId: string) {
  confirmingSubmit.value = true
  try {
    await confirmSubmission(opportunityId)
    await loadSubmissionPackage(opportunityId)
    await loadTrackingHistory(opportunityId)
    ElMessage.success('已确认提交！')
  } catch {
    ElMessage.error('确认提交失败')
  } finally { confirmingSubmit.value = false }
}

// ── 进度追踪 ──
async function loadTrackingHistory(opportunityId: string) {
  trackingLoading.value = true
  try {
    const result = await fetchTrackingHistory(opportunityId)
    trackingHistory.value = result.events || []
  } catch {
    trackingHistory.value = []
  } finally { trackingLoading.value = false }
}

function trackingEventLabel(eventType: string): string {
  const labels: Record<string, string> = {
    status_change: '状态变更', manual_update: '手动更新',
    system_check: '系统检测', note_added: '添加备注',
  }
  return labels[eventType] || eventType
}

// 行动卡片
const actionCards = [
  {
    title: '申报建议',
    icon: Lightning,
    color: 'icon-purple',
    lines: ['优先申报研发补贴'],
    matched: policyList.value.length > 0
      ? [`优先申报: ${policyList.value[0]?.name || '--'}`]
      : [],
  },
  {
    title: '下一步行动',
    icon: List,
    color: 'icon-green',
    lines: ['1. 确认资格', '2. 准备材料', '3. 在线申报', '4. 进度跟踪'],
    matched: ['1. 确认资格', '2. 准备材料', '3. 在线申报', '4. 进度跟踪'],
  },
  {
    title: '材料准备',
    icon: Document,
    color: 'icon-orange',
    lines: ['营业执照', '审计报告', '研发费用明细', '知识产权证明'],
    matched: ['营业执照', '审计报告', '研发费用明细', '知识产权证明'],
  },
  {
    title: 'AI 助手',
    icon: Service,
    color: 'icon-blue',
    lines: ['智能问答、政策解读'],
    matched: ['智能问答、政策解读'],
  },
]

// 🔄 页面恢复：从 localStorage 恢复上次匹配结果
function loadSavedResults() {
  try {
    const enterpriseId = localStorage.getItem('profile_enterprise_id') || localStorage.getItem('enterprise_id') || ''
    const saved = localStorage.getItem('workspace_matched_' + enterpriseId)
    if (saved) {
      const data = JSON.parse(saved)
      if (Date.now() - data.timestamp < 2 * 60 * 60 * 1000 && data.policies?.length > 0) {
        matchedPolicies.value = data.policies
        hasMatched.value = true
      }
    }
  } catch { /* ignore */ }
}

// 🗑 清除匹配结果
function clearResults() {
  matchedPolicies.value = []
  hasMatched.value = false
  showDetail.value = false
  selectedPolicy.value = null
  // 同时清除 localStorage 中的缓存
  const enterpriseId = localStorage.getItem('profile_enterprise_id') || localStorage.getItem('enterprise_id') || ''
  localStorage.removeItem('workspace_matched_' + enterpriseId)
}

// 金额分级样式
function amountClass(amount: string): string {
  if (!amount || amount === '待定') return 'amt-unknown'
  const match = amount.match(/(\d+)/)
  if (!match) return 'amt-low'
  const val = parseInt(match[1])
  if (val >= 500) return 'amt-max'
  if (val >= 200) return 'amt-high'
  if (val >= 50) return 'amt-mid'
  return 'amt-low'
}

onMounted(() => {
  loadProfile()
  loadSavedResults()
})
</script>

<style scoped lang="scss">
.workspace {
  position: relative;
  padding-bottom: var(--spacing-2xl);
  min-height: 100vh;
  background: url('@/assets/hero.png') center top/100% auto no-repeat;
  background-attachment: fixed;

  // 内容层覆盖在半透明遮罩上 — 极淡，让背景图清晰可见
  &::before {
    content: '';
    position: absolute;
    inset: 0;
    background: linear-gradient(180deg, rgba(248, 249, 253, 0.0) 0%, rgba(248, 249, 253, 0.6) 40%, var(--color-bg) 100%);
    pointer-events: none;
    z-index: 0;
  }

  > * {
    position: relative;
    z-index: 1;
  }
}

// ══════ 第1层：Hero ══════
.hero-section {
  position: relative;
  overflow: hidden;
  background: transparent;
  border-bottom: none;

  .hero-bg {
    display: none;
  }

  .hero-content {
    position: relative;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 56px 48px;
    max-width: 1400px;
    margin: 0 auto;
  }

  .hero-mascot {
    width: 380px;
    max-height: 320px;
    height: auto;
    flex-shrink: 0;
    filter: drop-shadow(0 4px 20px rgba(91, 77, 255, 0.1));
  }
}

.hero-left {
  .hero-title {
    font-size: var(--fs-hero-title);
    font-weight: var(--fw-bold);
    color: var(--color-text);
    margin: 0 0 4px;
    letter-spacing: -0.02em;
  }

  .hero-subtitle {
    font-size: var(--fs-section-title);
    font-weight: var(--fw-bold);
    color: var(--color-text);
    margin: 0 0 16px;

    .highlight {
      color: var(--color-primary);
    }
  }

  .hero-desc {
    font-size: var(--fs-body);
    font-weight: var(--fw-medium);
    color: var(--color-text-secondary);
    line-height: 1.8;
    max-width: 420px;
    margin: 0;
  }

  .hero-stats {
    display: flex;
    gap: 32px;

    .stat-item {
      display: flex;
      flex-direction: column;
      gap: 2px;

      .stat-value {
        font-size: var(--fs-section-title);
        font-weight: var(--fw-bold);
        color: var(--color-primary);
      }

      .stat-label {
        font-size: var(--fs-caption);
        color: var(--color-text-placeholder);
      }
    }
  }
}

// ══════ 第2层：核心三栏 ══════
.core-section {
  display: grid;
  grid-template-columns: 28% 42% 30%;
  gap: 20px;
  padding: 24px 48px;
  max-width: 1400px;
  margin: 0 auto;
}

.core-card {
  background: var(--color-card);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-sm);
  border: 1px solid var(--color-border-light);
  display: flex;
  flex-direction: column;

  .card-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 20px 24px 0;

    h3 {
      font-size: var(--fs-card-title);
      font-weight: var(--fw-semibold);
      color: var(--color-text);
      margin: 0;
    }

    .card-badge {
      font-size: 11px;
      padding: 3px 10px;
      border-radius: var(--radius-pill);
      background: rgba(34, 197, 94, 0.1);
      color: var(--color-success);
      font-weight: 500;
    }
  }

  .card-body {
    padding: 20px 24px;
    flex: 1;
  }

  .card-footer {
    padding: 0 24px 20px;
  }
}

// 企业画像卡片
.profile-card {
  .card-header {
    padding: 20px 24px 12px;

    .header-left {
      display: flex;
      align-items: center;
      gap: 10px;
    }

    h3 {
      font-size: var(--fs-card-title);
      font-weight: var(--fw-semibold);
      color: var(--color-text);
      margin: 0;
    }

    .card-badge {
      font-size: var(--fs-small);
      padding: 3px 10px;
      border-radius: var(--radius-pill);
      font-weight: var(--fw-medium);

      &.badge-complete {
        background: rgba(34, 197, 94, 0.1);
        color: var(--color-success);
      }

      &.badge-incomplete {
        background: rgba(245, 158, 11, 0.1);
        color: var(--color-warning);
      }
    }

    .btn-edit {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      padding: 4px 12px;
      border: 1px solid var(--color-border);
      border-radius: var(--radius-round);
      background: transparent;
      color: var(--color-text-secondary);
      font-size: var(--fs-caption);
      cursor: pointer;
      transition: all 0.15s;

      &:hover {
        border-color: var(--color-primary);
        color: var(--color-primary);
        background: rgba(91, 77, 255, 0.04);
      }
    }
  }

  .profile-body {
    padding: 8px 24px 16px;
    display: flex;
    flex-direction: column;
    gap: 0;
  }

  .profile-header-block {
    padding: 4px 0 14px;
    border-bottom: 1px solid var(--color-border-light);
    margin-bottom: 4px;

    .profile-name {
      font-size: var(--fs-card-title);
      font-weight: var(--fw-bold);
      color: var(--color-text);
      margin-bottom: 6px;
      line-height: 1.4;
    }

    .profile-region {
      display: flex;
      align-items: center;
      gap: 4px;
      font-size: var(--fs-label);
      color: var(--color-text-secondary);
    }
  }

  .profile-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 0;
    border-bottom: 1px solid var(--color-border-light);

    &:last-child {
      border-bottom: none;
    }

    .item-left {
      display: flex;
      align-items: center;
      gap: 12px;
    }

    .item-icon {
      width: 32px;
      height: 32px;
      border-radius: 10px;
      display: flex;
      align-items: center;
      justify-content: center;
      flex-shrink: 0;
      font-size: 16px;

      &.icon-purple { background: rgba(91, 77, 255, 0.1); color: var(--color-primary); }
      &.icon-blue   { background: rgba(99, 102, 241, 0.1); color: var(--color-info); }
      &.icon-green  { background: rgba(34, 197, 94, 0.1); color: var(--color-success); }
      &.icon-orange { background: rgba(245, 158, 11, 0.1); color: var(--color-warning); }
      &.icon-cyan   { background: rgba(6, 182, 212, 0.1); color: #06B6D4; }
    }

    .item-label {
      font-size: var(--fs-label);
      color: var(--color-text);
      font-weight: var(--fw-medium);
    }

    .item-value {
      font-size: var(--fs-label);
      color: var(--color-text);
      font-weight: var(--fw-medium);
      text-align: right;
      max-width: 55%;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;

      &.value-empty {
        display: inline-block;
        padding: 3px 12px;
        background: rgba(91, 77, 255, 0.08);
        color: var(--color-primary);
        border-radius: var(--radius-pill);
        font-size: var(--fs-caption);
        font-weight: var(--fw-medium);
        cursor: pointer;
        transition: background 0.15s;

        &:hover {
          background: rgba(91, 77, 255, 0.15);
        }
      }
    }

    .item-right {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      justify-content: flex-end;
      max-width: 55%;
    }

    .type-tag {
      font-size: var(--fs-small);
      padding: 3px 10px;
      border-radius: var(--radius-pill);
      background: rgba(91, 77, 255, 0.1);
      color: var(--color-primary);
      font-weight: var(--fw-medium);
      white-space: nowrap;
    }
  }

  .profile-footer {
    display: flex;
    flex-direction: column;
    gap: 10px;
    padding: 0 24px 20px;

    .btn-content {
      display: flex;
      align-items: center;
      gap: 8px;
      justify-content: center;
    }

    .footer-hint {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 4px;
      font-size: var(--fs-small);
      color: var(--color-text-placeholder);

      .hint-icon {
        font-size: var(--fs-label);
        color: var(--color-text-placeholder);
        cursor: help;
      }
    }
  }
}

.btn-primary-full {
  width: 100%;
  padding: 12px;
  border: none;
  border-radius: var(--radius-round);
  background: var(--color-primary-gradient);
  color: #fff;
  font-size: var(--fs-label);
  font-weight: var(--fw-semibold);
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;

  &:hover:not(:disabled) {
    background: linear-gradient(135deg, var(--color-primary-dark), var(--color-primary));
    box-shadow: 0 4px 16px rgba(91, 77, 255, 0.3);
    transform: translateY(-1px);
  }

  &:disabled {
    opacity: 0.7;
    cursor: not-allowed;
  }

  .btn-loading {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .spinner {
    width: 16px;
    height: 16px;
    border: 2px solid rgba(255,255,255,0.3);
    border-top-color: #fff;
    border-radius: 50%;
    animation: spin 0.6s linear infinite;
  }
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

// AI分析卡片
.analysis-card {
  .analysis-body {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    text-align: center;
  }
}

.analysis-empty {
  margin-bottom: 24px;

  .empty-illustration {
    margin-bottom: 16px;
    display: flex;
    justify-content: center;

    img {
      width: 180px;
      height: auto;
      display: block;
    }
  }

  .empty-title {
    font-size: var(--fs-body);
    font-weight: var(--fw-semibold);
    color: var(--color-text);
    margin: 0 0 6px;
  }

  .empty-desc {
    font-size: var(--fs-label);
    color: var(--color-text-placeholder);
    margin: 0;
  }
}

.analysis-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;

  .loading-engine {
    position: relative;
    width: 80px;
    height: 80px;

    .engine-ring {
      position: absolute;
      inset: 0;
      border-radius: 50%;
      border: 3px solid rgba(91, 77, 255, 0.12);
      border-top-color: var(--color-primary);
      animation: spin 1s linear infinite;
    }

    .engine-core {
      position: absolute;
      inset: 16px;
      border-radius: 50%;
      background: var(--color-primary-gradient);
      animation: pulse-core 1.5s ease-in-out infinite;
    }
  }

  @keyframes pulse-core {
    0%, 100% { transform: scale(0.85); opacity: 0.8; }
    50% { transform: scale(1.05); opacity: 1; }
  }

  .loading-text {
    font-size: var(--fs-label);
    color: var(--color-text-secondary);
    margin: 0;
  }
}

.analysis-complete {
  margin-bottom: 20px;

  .complete-icon {
    width: 48px;
    height: 48px;
    border-radius: 50%;
    background: linear-gradient(135deg, #22C55E, #16A34A);
    color: #fff;
    font-size: var(--fs-card-title);
    font-weight: var(--fw-bold);
    display: inline-flex;
    align-items: center;
    justify-content: center;
    margin-bottom: 12px;
  }

  .complete-title {
    font-size: var(--fs-body);
    font-weight: var(--fw-semibold);
    color: var(--color-text);
    margin: 0 0 4px;
  }

  .complete-desc {
    font-size: var(--fs-label);
    color: var(--color-text-secondary);
    margin: 0;
  }
}

.analysis-steps {
  display: flex;
  flex-direction: column;
  gap: 10px;
  width: 100%;
  max-width: 240px;

  .step {
    display: flex;
    align-items: center;
    gap: 10px;

    .step-dot {
      width: 10px;
      height: 10px;
      border-radius: 50%;
      background: var(--color-border);
      flex-shrink: 0;

      &.checked {
        background: var(--color-success);
      }
    }

    .step-text {
      font-size: var(--fs-label);
      color: var(--color-text-placeholder);
    }
  }

  &.done .step .step-text { color: var(--color-text-secondary); }
}

// 机会总览卡片
.overview-card {
  .overview-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 16px;
    height: 100%;
    align-content: start;
  }

  .ov-item {
    padding: 16px;
    border-radius: var(--radius-md);
    text-align: center;
    display: flex;
    flex-direction: column;
    gap: 4px;

    .ov-value {
      font-size: var(--fs-card-title);
      font-weight: var(--fw-bold);
    }

    .ov-label {
      font-size: var(--fs-caption);
      color: var(--color-text-placeholder);
    }
  }

  .ov-purple { background: rgba(91, 77, 255, 0.06); .ov-value { color: var(--color-primary); } }
  .ov-orange { background: rgba(245, 158, 11, 0.06); .ov-value { color: var(--color-warning); } }
  .ov-green  { background: rgba(34, 197, 94, 0.06); .ov-value { color: var(--color-success); } }
  .ov-blue   { background: rgba(99, 102, 241, 0.06); .ov-value { color: var(--color-info); } }
}

// ══════ 第3层：政策清单 ══════
.policy-section {
  max-width: 1400px;
  margin: 0 auto;
  padding: 0 48px 24px;

  .section-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 16px;

    h3 {
      font-size: var(--fs-card-title);
      font-weight: var(--fw-semibold);
      color: var(--color-text);
      margin: 0;
    }

    .btn-clear {
      font-size: 12px;
      color: var(--color-text-muted);
      cursor: pointer;
      text-decoration: underline;
      opacity: 0.6;
      &:hover { opacity: 1; }
    }

    .section-filters {
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .filter-chip {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      padding: 6px 14px;
      border: 1px solid var(--color-border);
      border-radius: var(--radius-pill);
      font-size: var(--fs-caption);
      color: var(--color-text-secondary);
      background: var(--color-card);
      cursor: pointer;
      transition: all 0.15s;

      &:hover {
        border-color: var(--color-primary);
        color: var(--color-primary);
      }
    }

    .btn-filter {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      padding: 6px 14px;
      border: 1px solid var(--color-border);
      border-radius: var(--radius-round);
      background: var(--color-card);
      color: var(--color-text-secondary);
      font-size: var(--fs-caption);
      cursor: pointer;
      transition: all 0.15s;

      &:hover {
        border-color: var(--color-primary);
        color: var(--color-primary);
      }
    }
  }
}

.policy-empty {
  text-align: center;
  padding: 60px 20px 48px;
  background: var(--color-card);
  border-radius: var(--radius-xl);
  border: 1px solid var(--color-border-light);

  .empty-illustration {
    width: 140px;
    height: auto;
    margin-bottom: 20px;
    display: block;
    margin-left: auto;
    margin-right: auto;
  }

  .empty-title {
    font-size: var(--fs-body);
    font-weight: var(--fw-semibold);
    color: var(--color-text);
    margin: 0 0 8px;
  }

  .empty-desc {
    font-size: var(--fs-label);
    color: var(--color-text-placeholder);
    margin: 0;
  }
}

.policy-table {
  background: var(--color-card);
  border-radius: var(--radius-xl);
  border: 1px solid var(--color-border-light);
  overflow: hidden;

  .table-header {
    display: grid;
    grid-template-columns: 2fr 0.9fr 0.8fr 0.7fr 0.8fr 0.7fr;
    gap: 12px;
    padding: 14px 24px;
    background: rgba(91, 77, 255, 0.03);
    border-bottom: 1px solid var(--color-border-light);
    font-size: var(--fs-caption);
    font-weight: var(--fw-semibold);
    color: var(--color-text-placeholder);
    text-transform: uppercase;
  }

  .table-body {
    .table-row {
      display: grid;
      grid-template-columns: 2fr 0.9fr 0.8fr 0.7fr 0.8fr 0.7fr;
      gap: 12px;
      padding: 16px 24px;
      border-bottom: 1px solid var(--color-border-light);
      align-items: center;
      font-size: var(--fs-label);
      transition: background 0.15s;

      &:last-child { border-bottom: none; }
      &:hover { background: rgba(91, 77, 255, 0.02); }
    }
  }

  .col-name {
    font-weight: var(--fw-medium);
    color: var(--color-text);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .col-match {
    display: flex;
    align-items: center;
    gap: 8px;

    .match-bar {
      flex: 1;
      height: 6px;
      border-radius: 3px;
      background: var(--color-border-light);
      overflow: hidden;

      .match-fill {
        height: 100%;
        border-radius: 3px;
        background: var(--color-primary-gradient);
        transition: width 0.6s ease;
      }
    }

    .match-text {
      font-size: var(--fs-caption);
      font-weight: var(--fw-semibold);
      color: var(--color-primary);
      min-width: 32px;
    }
  }

  .col-amount { color: var(--color-warning); font-weight: var(--fw-medium); }
  .col-dept { color: var(--color-text-secondary); }
  .col-deadline { color: var(--color-text-secondary); }

  .amount-tag {
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 13px;
    font-weight: var(--fw-semibold);
    &.amt-max { background: #fff2e8; color: #d46b08; border: 1px solid #ffd591; }
    &.amt-high { background: #fff7e6; color: #fa8c16; }
    &.amt-mid  { background: #f6ffed; color: #52c41a; }
    &.amt-low { color: var(--color-text-secondary); }
    &.amt-unknown { color: var(--color-text-muted); font-style: italic; }
  }

  .btn-sm {
    padding: 5px 14px;
    border: 1px solid var(--color-primary);
    border-radius: var(--radius-round);
    background: transparent;
    color: var(--color-primary);
    font-size: var(--fs-caption);
    font-weight: var(--fw-medium);
    cursor: pointer;
    transition: all 0.15s;

    &:hover {
      background: var(--color-primary);
      color: #fff;
    }
  }
}

// ══════ 第4层：四卡行动区 ══════
.action-section {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 20px;
  max-width: 1400px;
  margin: 0 auto;
  padding: 0 48px;
}

.action-card {
  background: var(--color-card);
  border-radius: var(--radius-xl);
  border: 1px solid var(--color-border-light);
  padding: 24px;
  box-shadow: var(--shadow-sm);

  .action-icon {
    width: 44px;
    height: 44px;
    border-radius: var(--radius-sm);
    display: flex;
    align-items: center;
    justify-content: center;
    margin-bottom: 12px;

    &.icon-purple { background: rgba(91, 77, 255, 0.1); color: var(--color-primary); }
    &.icon-green  { background: rgba(34, 197, 94, 0.1); color: var(--color-success); }
    &.icon-orange { background: rgba(245, 158, 11, 0.1); color: var(--color-warning); }
    &.icon-blue   { background: rgba(99, 102, 241, 0.1); color: var(--color-info); }
  }

  h4 {
    font-size: var(--fs-body);
    font-weight: var(--fw-semibold);
    color: var(--color-text);
    margin: 0 0 12px;
  }

  .action-content {
    p {
      font-size: var(--fs-label);
      color: var(--color-text-secondary);
      margin: 0 0 4px;
      line-height: 1.6;

      &:last-child { margin-bottom: 0; }
    }

    &.empty p {
      color: var(--color-text-placeholder);
    }
  }
}

// ══════ 响应式 ══════
@media (max-width: 1200px) {
  .hero-content { padding: 32px 24px; }
  .core-section {
    grid-template-columns: 1fr 1fr;
    padding: 24px;
  }
  .overview-card { display: none; }
  .action-section {
    grid-template-columns: 1fr 1fr;
    padding: 0 24px;
  }
  .policy-section { padding: 0 24px 24px; }
}

@media (max-width: 768px) {
  .hero-right { display: none; }
  .core-section {
    grid-template-columns: 1fr;
  }
  .action-section {
    grid-template-columns: 1fr;
  }
  .policy-table .table-header,
  .policy-table .table-body .table-row {
    grid-template-columns: 1.5fr 0.8fr 0.7fr 0.7fr;
  }
}

/* ====== 申报工作流弹窗 ====== */
.workflow-overlay {
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0,0,0,0.45);
  z-index: 1000;
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding: 40px 20px 60px;
  overflow-y: auto;
}

.workflow-dialog {
  background: var(--color-card);
  border-radius: var(--radius-xl);
  width: 100%;
  max-width: 780px;
  padding: 28px 32px 32px;
  box-shadow: 0 20px 60px rgba(0,0,0,0.15);
  position: relative;
  animation: wfSlideUp 0.3s ease;
}

@keyframes wfSlideUp {
  from { opacity: 0; transform: translateY(24px); }
  to { opacity: 1; transform: translateY(0); }
}

.workflow-header {
  display: flex; align-items: flex-start; justify-content: space-between;
  margin-bottom: 20px;
  .wf-title-row {
    h3 { font-size: var(--fs-card-title); font-weight: var(--fw-bold); color: var(--color-text); margin: 0 0 8px; }
    .wf-tags { display: flex; gap: 8px; flex-wrap: wrap; }
  }
  .wf-close {
    background: none; border: none; font-size: 24px; color: var(--color-text-placeholder);
    cursor: pointer; line-height: 1; padding: 0 4px;
    &:hover { color: var(--color-text); }
  }
}

.wf-meta-tag {
  padding: 3px 12px; border-radius: var(--radius-pill);
  font-size: var(--fs-caption); font-weight: var(--fw-medium);
  &.tag-green { background: rgba(34,197,94,0.1); color: var(--color-success); }
  &.tag-red { background: rgba(239,68,68,0.1); color: #EF4444; }
  &.tag-purple { background: var(--color-primary-bg); color: var(--color-primary); }
  &.tag-orange { background: rgba(245,158,11,0.1); color: var(--color-warning); }
}

.wf-step-content {
  min-height: 200px;
  padding: 16px 0 0;
}

.wf-step {
  animation: wfFadeIn 0.25s ease;
}

@keyframes wfFadeIn { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }

.wf-card {
  background: var(--color-bg);
  border-radius: var(--radius-md);
  padding: 20px;
  margin-bottom: 16px;
  h4 { font-size: var(--fs-label); font-weight: var(--fw-semibold); color: var(--color-text); margin: 0 0 12px; }
}

.wf-card-header {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 12px;
  h4 { margin: 0; }
}

// 按钮小组件
.btn-sm-outline {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 5px 14px; border: 1px solid var(--color-border); border-radius: var(--radius-round);
  background: var(--color-card); color: var(--color-text-secondary);
  font-size: var(--fs-caption); cursor: pointer; transition: all 0.15s;
  &:hover { border-color: var(--color-primary); color: var(--color-primary); }
  &.danger { &:hover { border-color: #EF4444; color: #EF4444; } }
}

.btn-sm-primary {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 5px 14px; border: none; border-radius: var(--radius-round);
  background: var(--color-primary); color: #fff;
  font-size: var(--fs-caption); font-weight: var(--fw-medium); cursor: pointer; transition: all 0.15s;
  &:hover { background: var(--color-primary-hover); }
  &:disabled { opacity: 0.6; cursor: not-allowed; }
}

.btn-primary-large {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 10px 24px; border: none; border-radius: var(--radius-round);
  background: var(--color-primary); color: #fff;
  font-size: var(--fs-label); font-weight: var(--fw-semibold); cursor: pointer; transition: all 0.15s;
  &:hover { background: var(--color-primary-hover); }
  &:disabled { opacity: 0.6; cursor: not-allowed; }
}

.btn-success-large {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 10px 24px; border: none; border-radius: var(--radius-round);
  background: #22C55E; color: #fff;
  font-size: var(--fs-label); font-weight: var(--fw-semibold); cursor: pointer; transition: all 0.15s;
  &:hover { background: #16A34A; }
  &:disabled { opacity: 0.6; cursor: not-allowed; }
}

.btn-sm-text {
  padding: 4px 8px; border: none; border-radius: var(--radius-round);
  background: transparent; color: var(--color-primary);
  font-size: var(--fs-caption); cursor: pointer;
  &:hover { background: var(--color-primary-bg); }
  &:disabled { opacity: 0.5; cursor: not-allowed; }
}

// 核验
.checks-grid {
  display: flex; flex-direction: column; gap: 10px;
}
.check-item {
  display: flex; align-items: flex-start; gap: 10px;
  padding: 10px 14px; border-radius: var(--radius-sm);
  background: var(--color-card);
  &.check-pass { border-left: 3px solid var(--color-success); }
  &.check-fail { border-left: 3px solid #EF4444; }
  &.check-unknown { border-left: 3px solid var(--color-warning); }
  .check-icon {
    width: 22px; height: 22px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: 12px; font-weight: 600; flex-shrink: 0;
  }
  &.check-pass .check-icon { background: rgba(34,197,94,0.12); color: var(--color-success); }
  &.check-fail .check-icon { background: rgba(239,68,68,0.12); color: #EF4444; }
  &.check-unknown .check-icon { background: rgba(245,158,11,0.12); color: var(--color-warning); }
  .check-text { flex: 1; font-size: var(--fs-label); color: var(--color-text); line-height: 1.5; }
  .check-hint {
    font-size: var(--fs-small); padding: 2px 8px; border-radius: var(--radius-pill); white-space: nowrap;
    &.hint-hard { background: rgba(239,68,68,0.08); color: #EF4444; }
    &.hint-soft { background: rgba(107,114,128,0.08); color: var(--color-text-secondary); }
  }
  .check-reason { font-size: var(--fs-caption); color: var(--color-text-secondary); margin-top: 2px; }
}

.ai-text {
  font-size: var(--fs-label); color: var(--color-text-secondary); line-height: 1.7;
  margin-bottom: 10px;
}

// 材料
.materials-tags {
  display: flex; flex-wrap: wrap; gap: 8px;
  .mat-tag {
    font-size: var(--fs-caption); padding: 4px 12px;
    border-radius: var(--radius-pill); background: var(--color-card);
    border: 1px solid var(--color-border-light); color: var(--color-text-secondary);
  }
}

.materials-progress-bar {
  display: flex; align-items: center; gap: 12px; margin-bottom: 14px;
  .progress-track {
    flex: 1; height: 10px; border-radius: 10px;
    background: var(--color-border-light); overflow: hidden;
    .progress-fill { height: 100%; border-radius: 10px; transition: width 0.4s ease; }
  }
  .progress-text { font-size: var(--fs-caption); font-weight: var(--fw-semibold); color: var(--color-text); min-width: 36px; text-align: right; }
}

.material-row {
  display: flex; align-items: center; gap: 10px;
  padding: 10px 0; border-bottom: 1px solid var(--color-border-light);
  &:last-child { border-bottom: none; }
  .mat-check {
    display: flex; align-items: center; gap: 8px; flex: 1; cursor: pointer;
    input[type="checkbox"] { width: 16px; height: 16px; accent-color: var(--color-primary); cursor: pointer; }
    .mat-name { font-size: var(--fs-label); color: var(--color-text); &.done { color: var(--color-text-secondary); text-decoration: line-through; } }
  }
  .mat-status-tag {
    font-size: var(--fs-small); padding: 2px 10px; border-radius: var(--radius-pill); white-space: nowrap;
    &.status-preparing { background: rgba(107,114,128,0.08); color: var(--color-text-secondary); }
    &.status-ready { background: rgba(34,197,94,0.08); color: var(--color-success); }
    &.status-submitted { background: var(--color-primary-bg); color: var(--color-primary); }
    &.status-waived { background: rgba(245,158,11,0.08); color: var(--color-warning); }
  }
  .mat-ai-tag {
    font-size: var(--fs-small); padding: 2px 8px; border-radius: var(--radius-pill);
    background: rgba(91,77,255,0.06); color: var(--color-primary);
  }
}

.mat-complete {
  text-align: center; padding: 12px; margin-top: 8px;
  background: rgba(34,197,94,0.06); border-radius: var(--radius-sm);
  font-size: var(--fs-label); font-weight: var(--fw-medium); color: var(--color-success);
}

.doc-list {
  display: flex; flex-direction: column; gap: 10px;
  .doc-row {
    display: flex; align-items: center; justify-content: space-between;
    padding: 12px; background: var(--color-card); border-radius: var(--radius-sm);
    .doc-info {
      display: flex; flex-direction: column; gap: 2px;
      .doc-name { font-size: var(--fs-label); font-weight: var(--fw-medium); color: var(--color-text); }
      .doc-meta { font-size: var(--fs-small); color: var(--color-text-placeholder); }
    }
    .doc-actions { display: flex; gap: 8px; }
  }
}

.wf-empty {
  text-align: center; padding: 20px; color: var(--color-text-placeholder); font-size: var(--fs-label);
}

// 提交
.info-grid {
  display: grid; grid-template-columns: 1fr 1fr; gap: 14px;
  .info-item {
    .info-label { display: block; font-size: var(--fs-caption); color: var(--color-text-placeholder); margin-bottom: 4px; }
    .info-value { font-size: var(--fs-label); color: var(--color-text); font-weight: var(--fw-medium);
      &.amount { color: var(--color-warning); font-weight: var(--fw-semibold); }
    }
  }
}

.status-row { margin-bottom: 16px; }
.status-badge {
  display: inline-block; padding: 6px 16px; border-radius: var(--radius-pill);
  font-size: var(--fs-label); font-weight: var(--fw-semibold);
  &.badge-info { background: rgba(107,114,128,0.1); color: var(--color-text-secondary); }
  &.badge-warning { background: rgba(245,158,11,0.12); color: var(--color-warning); }
  &.badge- { background: var(--color-primary-bg); color: var(--color-primary); }
  &.badge-success { background: rgba(34,197,94,0.12); color: var(--color-success); }
  &.badge-danger { background: rgba(239,68,68,0.1); color: #EF4444; }
}

.submit-area {
  padding: 16px; background: var(--color-card); border-radius: var(--radius-sm);
  .submit-hint { font-size: var(--fs-label); color: var(--color-text-secondary); margin: 0 0 12px; }
}

.package-ready {
  h4 { font-size: var(--fs-body); color: var(--color-success); margin: 0 0 8px; }
  .pkg-meta { display: flex; gap: 16px; margin-bottom: 12px;
    span { font-size: var(--fs-label); color: var(--color-text-secondary); }
  }
}

.status-result {
  padding: 12px 16px; border-radius: var(--radius-sm); margin-bottom: 12px;
  font-size: var(--fs-label); font-weight: var(--fw-medium);
  &.success { background: rgba(34,197,94,0.08); color: var(--color-success); }
  &.fail { background: rgba(239,68,68,0.08); color: #EF4444; }
}

.tracking-panel {
  .tracking-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px;
    h4 { margin: 0; }
  }
  .tracking-timeline {
    display: flex; flex-direction: column; gap: 0;
    .timeline-item {
      display: flex; gap: 12px; padding: 8px 0;
      .timeline-dot {
        width: 10px; height: 10px; border-radius: 50%;
        background: var(--color-primary); margin-top: 6px; flex-shrink: 0;
      }
      .timeline-content {
        flex: 1; padding-bottom: 8px; border-bottom: 1px solid var(--color-border-light);
        .timeline-title { font-size: var(--fs-label); font-weight: var(--fw-medium); color: var(--color-text); }
        .timeline-note { font-size: var(--fs-caption); color: var(--color-text-secondary); margin-top: 2px; }
        .timeline-time { font-size: var(--fs-small); color: var(--color-text-placeholder); margin-top: 4px; }
      }
    }
  }
  .timeline-empty { text-align: center; padding: 16px; color: var(--color-text-placeholder); font-size: var(--fs-label); }
}

// 日历
.deadline-card {
  display: flex; align-items: center; gap: 14px;
  padding: 16px 20px; background: var(--color-card); border-radius: var(--radius-md);
  margin-bottom: 12px;
  .deadline-icon { font-size: 28px; }
  .deadline-info {
    .deadline-label { display: block; font-size: var(--fs-caption); color: var(--color-text-placeholder); }
    .deadline-value { font-size: var(--fs-body); font-weight: var(--fw-semibold); color: var(--color-text); }
  }
  &.no-deadline { color: var(--color-text-placeholder); font-size: var(--fs-label); }
}

.calendar-cta {
  text-align: center; padding: 8px 0;
  .calendar-hint {
    margin-top: 10px; font-size: var(--fs-caption); color: var(--color-text-placeholder);
  }
}

// 步骤导航
.wf-nav {
  display: flex; align-items: center; justify-content: space-between;
  padding: 16px 0 0; border-top: 1px solid var(--color-border-light);
  .btn-nav {
    display: inline-flex; align-items: center; gap: 4px;
    padding: 8px 20px; border: 1px solid var(--color-border); border-radius: var(--radius-round);
    background: var(--color-card); color: var(--color-text-secondary);
    font-size: var(--fs-label); cursor: pointer; transition: all 0.15s;
    &:hover:not(:disabled) { border-color: var(--color-primary); color: var(--color-primary); }
    &:disabled { opacity: 0.4; cursor: not-allowed; }
    &.primary {
      background: var(--color-primary); border-color: var(--color-primary); color: #fff;
      &:hover:not(:disabled) { background: var(--color-primary-hover); }
    }
  }
  .step-indicator { font-size: var(--fs-caption); color: var(--color-text-placeholder); }
}
</style>
