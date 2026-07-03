<template>
  <div class="profile-page">
    <div class="page-header">
      <h1>企业画像配置</h1>
      <p class="page-desc">完善企业信息，提高政策匹配精度。定时推送将自动使用此画像。</p>
    </div>

    <!-- 加载中 -->
    <div v-if="loading" class="loading-wrap">
      <el-skeleton :rows="8" animated />
    </div>

    <template v-else>
      <!-- 当前企业画像 -->
      <div v-if="hasSaved" class="profile-card current-profile">
        <div class="profile-card-header">
          <span class="profile-card-title">当前企业画像</span>
          <el-tag size="small" type="success" effect="plain">已配置</el-tag>
        </div>
        <div class="profile-grid">
          <div class="profile-item">
            <span class="profile-label">地区</span>
            <span class="profile-value">{{ form.region || '-' }}</span>
          </div>
          <div class="profile-item">
            <span class="profile-label">企业类型</span>
            <span class="profile-value">{{ form.company_type || '-' }}</span>
          </div>
          <div class="profile-item">
            <span class="profile-label">行业</span>
            <span class="profile-value">{{ form.industry || '-' }}</span>
          </div>
          <div class="profile-item">
            <span class="profile-label">员工人数</span>
            <span class="profile-value">{{ form.employees ? form.employees + '人' : '-' }}</span>
          </div>
          <div class="profile-item">
            <span class="profile-label">年营收</span>
            <span class="profile-value">{{ form.annual_revenue ? form.annual_revenue + '万元' : '-' }}</span>
          </div>
          <div class="profile-item">
            <span class="profile-label">成立时间</span>
            <span class="profile-value">{{ form.established_date || '-' }}</span>
          </div>
          <div class="profile-item">
            <span class="profile-label">高新技术企业</span>
            <span class="profile-value">{{ form.is_high_tech === true ? '是' : form.is_high_tech === false ? '否' : '-' }}</span>
          </div>
          <div class="profile-item">
            <span class="profile-label">中小微企业</span>
            <span class="profile-value">{{ form.is_sme === true ? '是' : form.is_sme === false ? '否' : '-' }}</span>
          </div>
          <div class="profile-item">
            <span class="profile-label">专利数量</span>
            <span class="profile-value">{{ form.patents != null ? form.patents + '件' : '-' }}</span>
          </div>
          <div class="profile-item">
            <span class="profile-label">注册资本</span>
            <span class="profile-value">{{ form.registered_capital ? form.registered_capital + '万元' : '-' }}</span>
          </div>
          <div class="profile-item">
            <span class="profile-label">研发占比</span>
            <span class="profile-value">{{ form.rd_ratio != null ? form.rd_ratio + '%' : '-' }}</span>
          </div>
          <div class="profile-item">
            <span class="profile-label">目标补贴</span>
            <span class="profile-value">{{ form.target_subsidy || '-' }}</span>
          </div>
          <div class="profile-item" v-if="form.qualifications && form.qualifications.length">
            <span class="profile-label">资质标签</span>
            <div class="tag-row">
              <el-tag v-for="q in form.qualifications" :key="q" size="small" type="info" effect="plain">{{ q }}</el-tag>
            </div>
          </div>
          <div class="profile-item" v-if="form.intent_summary">
            <span class="profile-label">意图摘要</span>
            <span class="profile-value note-text">{{ form.intent_summary }}</span>
          </div>
          <div class="profile-item" v-if="form.extra_note">
            <span class="profile-label">备注</span>
            <span class="profile-value note-text">{{ form.extra_note }}</span>
          </div>
        </div>
      </div>

      <!-- 编辑表单 -->
      <div class="profile-card form-card">
        <div class="profile-card-header">
          <span class="profile-card-title">{{ hasSaved ? '编辑画像' : '新建画像' }}</span>
          <el-button text size="small" type="primary" @click="showNlu = !showNlu" style="margin-left:auto;">
            {{ showNlu ? '收起快速导入' : '快速导入' }}
          </el-button>
        </div>

        <!-- NLU 快速导入 -->
        <div v-if="showNlu" class="nlu-section">
          <el-input
            v-model="nluText"
            type="textarea"
            :rows="3"
            placeholder="粘贴企业简介，AI 自动提取画像字段（如：XX公司是深圳的高新技术企业，员工200人，年营收5000万...）"
          />
          <el-button
            type="primary"
            size="small"
            :loading="nluLoading"
            @click="handleNlu"
            style="margin-top:10px;"
          >
            提取并补全
          </el-button>
        </div>

        <el-form
          :model="form"
          label-width="0"
          size="large"
          @submit.prevent="handleSave"
          class="profile-form"
        >
          <el-collapse v-model="activePanels" class="form-sections">
            <!-- 📋 基础信息 -->
            <el-collapse-item name="basic" title="📋 基础信息">
              <div class="section-grid">
                <div class="field-group">
                  <span class="field-label required">地区</span>
                  <el-input v-model="form.region" placeholder="如：深圳市" class="field-input" />
                </div>
                <div class="field-group">
                  <span class="field-label required">企业类型</span>
                  <el-input v-model="form.company_type" placeholder="如：科技型中小企业" class="field-input" />
                </div>
                <div class="field-group">
                  <span class="field-label required">行业</span>
                  <el-input v-model="form.industry" placeholder="如：人工智能" class="field-input" />
                </div>
              </div>
            </el-collapse-item>

            <!-- 📊 规模信息 -->
            <el-collapse-item name="scale" title="📊 规模信息">
              <div class="section-grid">
                <div class="field-group">
                  <span class="field-label">员工人数</span>
                  <el-input-number v-model="form.employees" :min="0" :max="999999" placeholder="如：200" controls-position="right" class="field-input-number" />
                </div>
                <div class="field-group">
                  <span class="field-label">年营收（万元）</span>
                  <el-input-number v-model="form.annual_revenue" :min="0" :precision="1" placeholder="如：5000" controls-position="right" class="field-input-number" />
                </div>
                <div class="field-group">
                  <span class="field-label">成立时间</span>
                  <el-date-picker
                    v-model="form.established_date"
                    type="month"
                    placeholder="选择年月"
                    format="YYYY-MM"
                    value-format="YYYY-MM"
                    class="field-date"
                  />
                </div>
              </div>
            </el-collapse-item>

            <!-- 🏅 资质信息 -->
            <el-collapse-item name="qual" title="🏅 资质信息">
              <div class="section-grid">
                <div class="field-group inline-field">
                  <span class="field-label">高新技术企业</span>
                  <el-switch v-model="form.is_high_tech" :active-value="true" :inactive-value="false" />
                </div>
                <div class="field-group inline-field">
                  <span class="field-label">中小微企业</span>
                  <el-switch v-model="form.is_sme" :active-value="true" :inactive-value="false" />
                </div>
                <div class="field-group">
                  <span class="field-label">专利数量</span>
                  <el-input-number v-model="form.patents" :min="0" :max="99999" placeholder="如：15" controls-position="right" class="field-input-number" />
                </div>
                <div class="field-group field-span">
                  <span class="field-label">资质标签</span>
                  <div class="tag-input-wrap">
                    <el-tag
                      v-for="(tag, idx) in form.qualifications"
                      :key="idx"
                      closable
                      size="small"
                      @close="removeQualification(idx)"
                      style="margin-right:6px;margin-bottom:4px;"
                    >
                      {{ tag }}
                    </el-tag>
                    <el-input
                      v-if="tagInputVisible"
                      ref="tagInputRef"
                      v-model="tagInputValue"
                      size="small"
                      @keyup.enter="addQualification"
                      @blur="addQualification"
                      style="width:120px;"
                    />
                    <el-button v-else size="small" @click="showTagInput">+ 添加</el-button>
                  </div>
                </div>
              </div>
            </el-collapse-item>

            <!-- 💰 经营信息 -->
            <el-collapse-item name="finance" title="💰 经营信息">
              <div class="section-grid">
                <div class="field-group">
                  <span class="field-label">注册资本（万元）</span>
                  <el-input-number v-model="form.registered_capital" :min="0" :precision="0" placeholder="如：1000" controls-position="right" class="field-input-number" />
                </div>
                <div class="field-group">
                  <span class="field-label">研发费用占比（%）</span>
                  <el-input-number v-model="form.rd_ratio" :min="0" :max="100" :precision="1" placeholder="如：8.5" controls-position="right" class="field-input-number" />
                </div>
              </div>
            </el-collapse-item>

            <!-- 🎯 目标 & 备注 -->
            <el-collapse-item name="target" title="🎯 目标与备注">
              <div class="section-grid">
                <div class="field-group">
                  <span class="field-label">目标补贴类型</span>
                  <el-input v-model="form.target_subsidy" placeholder="如：融资补贴、人才补贴" class="field-input" />
                </div>
                <div class="field-group">
                  <span class="field-label">意图摘要</span>
                  <el-input v-model="form.intent_summary" type="textarea" :rows="2" placeholder="可选，简述企业申报意图" class="field-input" />
                </div>
                <div class="field-group field-span">
                  <span class="field-label">备注</span>
                  <el-input v-model="form.extra_note" type="textarea" :rows="2" placeholder="可选，填写额外说明" class="field-input" />
                </div>
              </div>
            </el-collapse-item>
          </el-collapse>

          <div class="form-actions">
            <el-button
              type="primary"
              size="large"
              @click="handleSave"
              :loading="saving"
              round
              class="save-btn"
            >
              保存配置
            </el-button>
          </div>
        </el-form>
      </div>

      <!-- 定时推送说明 -->
      <div class="profile-card info-card">
        <div class="info-body">
          <div class="info-dot"></div>
          <div class="info-text">
            <span class="info-title">定时推送已启用</span>
            <span class="info-desc">后端自动执行定时推送任务，将使用此企业画像匹配新发布的政策。</span>
          </div>
          <el-button text size="small" @click="$router.push('/push-records')" class="info-link">
            查看推送记录 →
          </el-button>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import type { EnterpriseProfile } from '../types/push'
import { fetchEnterprises, createEnterprise, fetchEnterpriseProfile, saveEnterpriseProfile, nluEnterpriseProfile } from '../api/advisor'

const loading = ref(true)
const saving = ref(false)
const hasSaved = ref(false)
const enterpriseId = ref('')
const activePanels = ref(['basic', 'scale', 'qual', 'finance', 'target'])

// NLU 快速导入
const showNlu = ref(false)
const nluLoading = ref(false)
const nluText = ref('')

// 资质标签输入
const tagInputVisible = ref(false)
const tagInputValue = ref('')
const tagInputRef = ref()

const form = reactive<EnterpriseProfile>({
  region: null,
  company_type: null,
  industry: null,
  employees: null,
  annual_revenue: null,
  established_date: null,
  is_high_tech: null,
  is_sme: null,
  patents: null,
  qualifications: [],
  registered_capital: null,
  rd_ratio: null,
  intent_summary: '',
  target_subsidy: null,
  extra_note: '',
})

// ── 初始化：自动找/建默认企业 ──
async function ensureEnterprise(): Promise<string> {
  // 1. 尝试从 localStorage 恢复
  const cached = localStorage.getItem('profile_enterprise_id')
  if (cached) {
    try {
      await fetchEnterpriseProfile(cached)
      return cached  // ID 有效
    } catch {
      localStorage.removeItem('profile_enterprise_id')  // ID 失效，清除
    }
  }

  // 2. 查已有企业列表
  try {
    const list = await fetchEnterprises()
    if (list.enterprises && list.enterprises.length > 0) {
      const id = list.enterprises[0].enterprise_id
      localStorage.setItem('profile_enterprise_id', id)
      return id
    }
  } catch {
    // 列表获取失败，继续尝试创建
  }

  // 3. 没有则创建一个默认企业
  const created: any = await createEnterprise('默认企业')
  localStorage.setItem('profile_enterprise_id', created.enterprise_id)
  return created.enterprise_id
}

// ── 从 API 加载画像到表单 ──
function applyProfile(raw: Record<string, unknown>) {
  form.region = (raw.region as string) || null
  form.company_type = (raw.company_type as string) || null
  form.industry = (raw.industry as string) || null
  form.employees = (raw.employees as number) ?? null
  form.annual_revenue = (raw.annual_revenue as number) ?? null
  form.established_date = (raw.established_date as string) || null
  form.is_high_tech = (raw.is_high_tech as boolean) ?? null
  form.is_sme = (raw.is_sme as boolean) ?? null
  form.patents = (raw.patents as number) ?? null
  form.qualifications = (raw.qualifications as string[]) || []
  form.registered_capital = (raw.registered_capital as number) ?? null
  form.rd_ratio = (raw.rd_ratio as number) ?? null
  form.intent_summary = (raw.intent_summary as string) || ''
  form.target_subsidy = (raw.target_subsidy as string) || null
  form.extra_note = (raw.extra_note as string) || ''
}

onMounted(async () => {
  try {
    enterpriseId.value = await ensureEnterprise()
    const result = await fetchEnterpriseProfile(enterpriseId.value)
    const profile = (result as any).profile || {}
    applyProfile(profile)
    hasSaved.value = !!(profile.region || profile.company_type || profile.industry)
  } catch (e: any) {
    ElMessage.error('加载企业画像失败: ' + (e.message || '未知错误'))
  } finally {
    loading.value = false
  }
})

async function handleSave() {
  if (!enterpriseId.value) {
    ElMessage.error('企业信息未就绪，请刷新页面后重试')
    return
  }
  saving.value = true
  try {
    await saveEnterpriseProfile(enterpriseId.value, { ...form })
    hasSaved.value = true
    ElMessage.success('企业画像已保存')
  } catch (e: any) {
    ElMessage.error('保存失败: ' + (e.message || '未知错误'))
  } finally {
    saving.value = false
  }
}

// ── NLU 快速导入 ──
async function handleNlu() {
  if (!nluText.value.trim()) return
  nluLoading.value = true
  try {
    const result: any = await nluEnterpriseProfile(enterpriseId.value, nluText.value)
    const profile = result.profile
    if (profile) {
      applyProfile(profile)
    }
    ElMessage.success('信息提取完成，请核对后保存')
  } catch (e: any) {
    ElMessage.error('提取失败: ' + (e.message || '未知错误'))
  } finally {
    nluLoading.value = false
  }
}

// ── 资质标签操作 ──
function showTagInput() {
  tagInputVisible.value = true
  nextTick(() => { tagInputRef.value?.focus() })
}

function addQualification() {
  const val = tagInputValue.value.trim()
  if (val && !form.qualifications.includes(val)) {
    form.qualifications.push(val)
  }
  tagInputVisible.value = false
  tagInputValue.value = ''
}

function removeQualification(idx: number) {
  form.qualifications.splice(idx, 1)
}
</script>

<style scoped lang="scss">
.profile-page {
  max-width: 720px;
  margin: 0 auto;
  padding: 24px 32px;
}

.page-header {
  margin-bottom: 28px;

  h1 {
    font-size: 20px;
    font-weight: 600;
    color: #222;
    margin: 0;
  }
  .page-desc {
    font-size: 13px;
    color: #999;
    margin-top: 6px;
    line-height: 1.5;
  }
}

.loading-wrap {
  background: #fff;
  border-radius: 16px;
  padding: 32px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.04);
}

/* ── 卡片通用 ── */
.profile-card {
  background: #fff;
  border-radius: 16px;
  padding: 24px;
  margin-bottom: 16px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.04);

  .profile-card-header {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 20px;

    .profile-card-title {
      font-size: 15px;
      font-weight: 500;
      color: #333;
    }
  }
}

/* ── 当前画像展示 ── */
.current-profile {
  border: 1px solid #d1fae5;
  background: linear-gradient(135deg, #f0fdf4 0%, #fff 100%);
}

.profile-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px 24px;

  .profile-item {
    display: flex;
    flex-direction: column;
    gap: 3px;

    .profile-label {
      font-size: 11px;
      color: #999;
      font-weight: 500;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }
    .profile-value {
      font-size: 14px;
      color: #333;
      font-weight: 500;
    }
    .note-text {
      font-weight: 400;
      color: #666;
    }
    .tag-row {
      display: flex;
      flex-wrap: wrap;
      gap: 4px;
    }
  }
}

/* ── NLU 快速导入 ── */
.nlu-section {
  background: #f0f7ff;
  border: 1px solid #dbeafe;
  border-radius: 12px;
  padding: 14px 16px;
  margin-bottom: 20px;
}

/* ── 表单区 ── */
.form-card {
  .form-sections {
    margin-bottom: 0;

    :deep(.el-collapse-item__header) {
      font-size: 14px;
      font-weight: 500;
      color: #444;
      border: none;
      background: transparent;
      padding: 4px 0;
      &.is-active {
        margin-bottom: 8px;
      }
    }
    :deep(.el-collapse-item__wrap) {
      border: none;
      background: transparent;
    }
    :deep(.el-collapse-item__content) {
      padding-bottom: 16px;
    }
  }

  .section-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 16px 20px;

    .field-span {
      grid-column: 1 / -1;
    }
  }

  .field-group {
    display: flex;
    flex-direction: column;
    gap: 5px;

    &.inline-field {
      flex-direction: row;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
    }

    .field-label {
      font-size: 12px;
      color: #666;
      font-weight: 500;

      &.required::after {
        content: ' *';
        color: #f56c6c;
      }
    }

    .field-input {
      :deep(.el-input__wrapper) {
        border-radius: 10px;
        border: 1px solid #e5e7eb;
        background: #f9fafb;
        box-shadow: none;
        height: 40px;
        padding: 0 12px;
        transition: all 0.2s;
        &:hover { border-color: #d0d0d0; background: #fff; }
        &.is-focus {
          border-color: #3b82f6;
          background: #fff;
          box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.08);
        }
      }
      :deep(.el-input__inner) {
        font-size: 13px; color: #333;
        &::placeholder { color: #bbb; font-size: 12px; }
      }
      :deep(.el-textarea__inner) {
        border-radius: 10px;
        border: 1px solid #e5e7eb;
        background: #f9fafb;
        font-size: 13px;
        box-shadow: none;
        &:hover { border-color: #d0d0d0; background: #fff; }
        &:focus {
          border-color: #3b82f6;
          background: #fff;
          box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.08);
        }
      }
    }

    .field-input-number {
      :deep(.el-input-number) { width: 100%; }
      :deep(.el-input__wrapper) {
        border-radius: 10px;
        border: 1px solid #e5e7eb;
        background: #f9fafb;
        box-shadow: none;
        height: 40px;
        padding: 0 12px;
        transition: all 0.2s;
        &:hover { border-color: #d0d0d0; background: #fff; }
        &.is-focus {
          border-color: #3b82f6;
          background: #fff;
          box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.08);
        }
      }
      :deep(.el-input__inner) {
        font-size: 13px; color: #333; text-align: left;
        &::placeholder { color: #bbb; font-size: 12px; }
      }
    }

    .field-date {
      :deep(.el-input__wrapper) {
        border-radius: 10px;
        border: 1px solid #e5e7eb;
        background: #f9fafb;
        box-shadow: none;
        height: 40px;
        transition: all 0.2s;
        &:hover { border-color: #d0d0d0; background: #fff; }
        &.is-focus {
          border-color: #3b82f6;
          background: #fff;
          box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.08);
        }
      }
      :deep(.el-input__inner) { font-size: 13px; &::placeholder { color: #bbb; font-size: 12px; } }
    }

    .tag-input-wrap {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 2px;
      min-height: 36px;
      padding: 6px 10px;
      background: #f9fafb;
      border: 1px solid #e5e7eb;
      border-radius: 10px;
    }
  }
}

.form-actions {
  margin-top: 4px;
  padding-top: 20px;
  border-top: 1px solid #f3f4f6;

  .save-btn {
    width: 100%;
    height: 46px;
    font-size: 14px;
    font-weight: 500;
    border: none;
    box-shadow: 0 2px 8px rgba(59, 130, 246, 0.15);
    transition: box-shadow 0.2s;
    &:hover { box-shadow: 0 4px 14px rgba(59, 130, 246, 0.25); }
  }
}

/* ── 推送说明 ── */
.info-card {
  background: #f9fafb;
  border: 1px solid #e5e7eb;

  .info-body {
    display: flex;
    align-items: center;
    gap: 12px;

    .info-dot {
      width: 8px; height: 8px; border-radius: 50%;
      background: #10b981; flex-shrink: 0;
    }
    .info-text {
      flex: 1;
      display: flex; flex-direction: column; gap: 2px;
      .info-title { font-size: 13px; font-weight: 500; color: #333; }
      .info-desc { font-size: 12px; color: #999; line-height: 1.4; }
    }
    .info-link {
      font-size: 12px; color: #3b82f6; flex-shrink: 0;
      &:hover { color: #2563eb; }
    }
  }
}
</style>
