"""注入演示数据：企业画像 + 静态匹配结果"""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.db.database import Database
from config.settings import settings

db = Database(db_path=settings.DATABASE_FILE)

# 1. 创建演示企业
enterprise_id = "demo_20260615"
profile = {
    "region": "深圳市南山区",
    "company_type": "民营科技企业",
    "industry": "人工智能 / 信息技术",
    "employees": 380,
    "annual_revenue": 1.2,
    "established_date": "2018-05",
    "is_high_tech": True,
    "is_sme": True,
    "patents": 45,
    "qualifications": ["高新技术企业", "专精特新中小企业", "软件企业"],
    "registered_capital": 5000,
    "rd_ratio": 0.18,
    "intent_summary": "希望申请 AI 产业研发补贴和中小企业贷款贴息",
}
db.create_enterprise(enterprise_id=enterprise_id, name="深圳智创科技有限公司", profile_json=json.dumps(profile, ensure_ascii=False))
print(f"Enterprise created: {enterprise_id}")

# 2. 静态匹配结果
pols = [
    dict(name="深圳市研发投入补助计划项目管理办法", match=95, amount="最高 500 万元", department="深圳市科技创新局", deadline="2026-09-30",
         match_explanation="企业研发占比 18%，远超 5% 门槛；拥有 45 项专利，符合高新技术企业认定",
         suggestions=["建议优先申报", "准备好近三年研发费用审计报告", "注意年度 R&D 统计填报"],
         eligibility_checks=[
             dict(condition="深圳注册", result="pass", detail="南山区注册企业，符合"),
             dict(condition="高新技术企业", result="pass", detail="已认证高新技术企业"),
             dict(condition="研发占比 >= 5%", result="pass", detail="实际 18%，远超标准"),
             dict(condition="年营收 >= 1000 万", result="pass", detail="年营收 1.2 亿"),
         ],
         amount_detail="按研发费用 30% 补助，上限 500 万/年",
         application_platform="深圳市科技业务管理系统",
         contact="市科创局 0755-88123456"),
    dict(name="深圳市 AI+先进制造业行动计划配套资金", match=92, amount="最高 300 万元", department="深圳市工业和信息化局", deadline="2026-10-15",
         match_explanation="企业属于 AI 产业方向，符合人工智能+先进制造重点支持领域",
         suggestions=["准备 AI 产品落地案例", "提供与制造业企业合作协议"],
         eligibility_checks=[
             dict(condition="AI 相关产业", result="pass", detail="主营人工智能技术研发"),
             dict(condition="深圳注册", result="pass", detail="南山区注册企业"),
             dict(condition="有落地案例", result="pass", detail="已有客户案例"),
             dict(condition="营收要求", result="pass", detail="年营收 1.2 亿"),
         ],
         amount_detail="示范项目补助 100-300 万，按实际投入 30% 核定",
         application_platform="深圳市工信局项目申报系统",
         contact="市工信局 0755-88234567"),
    dict(name="深圳市中小微企业贷款贴息政策", match=88, amount="最高 100 万元", department="深圳市中小企业服务局", deadline="2026-12-31",
         match_explanation="企业符合专精特新中小企业认定，可享受贷款利息 50% 补贴",
         suggestions=["准备银行贷款合同及利息凭证", "注意贴息上限和申报批次"],
         eligibility_checks=[
             dict(condition="中小微企业", result="pass", detail="380 人，年营收 1.2 亿，属中型企业"),
             dict(condition="专精特新认定", result="pass", detail="已获专精特新中小企业认定"),
             dict(condition="深圳注册", result="pass", detail="南山区注册企业"),
             dict(condition="有银行贷款", result="unknown", detail="需提供贷款证明"),
         ],
         amount_detail="按贷款利息 50% 补贴，单笔最高 100 万",
         application_platform="深i企平台",
         contact="市中小企业服务局 0755-88345678"),
    dict(name="广东省促进人工智能产业创新发展若干措施", match=82, amount="最高 200 万元", department="广东省工业和信息化厅", deadline="2026-08-31",
         match_explanation="被认定为省级人工智能重点企业，可申请研发平台补贴和技术攻关资助",
         suggestions=["准备省级技术创新中心认定材料", "提交近两年 AI 研发项目清单"],
         eligibility_checks=[
             dict(condition="AI 产业方向", result="pass", detail="主营 AI 技术研发"),
             dict(condition="广东省注册", result="pass", detail="深圳市属广东省"),
             dict(condition="研发团队 >= 50 人", result="pass", detail="研发人员占比超 60%"),
             dict(condition="营收 >= 5000 万", result="pass", detail="年营收 1.2 亿"),
         ],
         amount_detail="技术攻关项目最高 200 万，研发平台最高 100 万",
         application_platform="广东省科技业务管理阳光政务平台",
         contact="省工信厅 020-83112233"),
    dict(name="国家专精特新小巨人企业培育资金", match=75, amount="最高 600 万元", department="工业和信息化部", deadline="2026-11-30",
         match_explanation="企业已是省级专精特新，下一步可冲刺国家级小巨人认定",
         suggestions=["先申请省级专精特新升级评审", "准备近两年市场占有率证明", "补充核心专利清单"],
         eligibility_checks=[
             dict(condition="专精特新中小企业", result="pass", detail="已认定"),
             dict(condition="主导产品市占率", result="unknown", detail="需提供第三方市占率证明"),
             dict(condition="核心专利数", result="pass", detail="45 项有效专利"),
             dict(condition="研发投入", result="pass", detail="18% 远超门槛"),
         ],
         amount_detail="国家级小巨人最高奖补 600 万（中央+地方配套）",
         application_platform="优质中小企业梯度培育平台",
         contact="市中小企业服务局 0755-88345678"),
    dict(name="深圳市南山区科技创新发展专项资金", match=90, amount="最高 150 万元", department="南山区科技创新局", deadline="2026-07-15",
         match_explanation="南山区注册的科技型企业，可直接申请区级配套补贴",
         suggestions=["优先申报（7 月截止，时间紧迫）", "区级流程通常较快"],
         eligibility_checks=[
             dict(condition="南山区注册", result="pass", detail="注册地在南山区"),
             dict(condition="高新技术企业", result="pass", detail="已认证"),
             dict(condition="科技型企业", result="pass", detail="AI 研发企业"),
         ],
         amount_detail="区级配套最高 150 万，市级项目额外 30% 配套",
         application_platform="南山区科技创新局官网",
         contact="南山区科创局 0755-26551234"),
    dict(name="深圳市稳定和促进就业创业扶持政策", match=68, amount="每年 5-20 万元", department="深圳市人力资源和社会保障局", deadline="2026-12-31",
         match_explanation="企业用工规模达标，可享受稳岗补贴和社保减免",
         suggestions=["确认社保缴纳情况", "注意年度申报时间窗口"],
         eligibility_checks=[
             dict(condition="深圳注册", result="pass", detail="南山区注册企业"),
             dict(condition="员工 >= 30 人", result="pass", detail="现有 380 人"),
             dict(condition="无裁员记录", result="unknown", detail="需提供上年度裁员情况说明"),
             dict(condition="正常缴纳社保", result="pass", detail="已核查"),
         ],
         amount_detail="稳岗补贴按上年度失业保险缴费 50% 返还",
         application_platform="深圳市人社局网上办事大厅",
         contact="市人社局 0755-12333"),
]

print(f"Static policies: {len(pols)}")

# 3. 输出 JS 注入脚本
js = '// 演示数据注入 - 在浏览器 Console 运行即可\n'
js += f'localStorage.setItem("profile_enterprise_id", "{enterprise_id}");\n'
js += f'localStorage.setItem("workspace_matched_{enterprise_id}", JSON.stringify({{\n'
js += f'  "policies": {json.dumps(pols, ensure_ascii=False)},\n'
js += f'  "profileData": {json.dumps(profile, ensure_ascii=False)},\n'
js += f'  "timestamp": Date.now()\n'
js += f'}}));\n'
js += 'console.log("Demo data injected! Refresh the page.");\n'

with open("data/demo_inject.js", "w", encoding="utf-8") as f:
    f.write(js)
print("JS inject script: data/demo_inject.js")
db.close()
print("\nDone! Steps:")
print("  1. Start backend: python -m src.api.main --serve")
print("  2. Start frontend: npm run dev")
print("  3. Open http://localhost:5173")
print("  4. F12 -> Console -> paste data/demo_inject.js -> Enter")
print("  5. Refresh page -> see 7 matched policies")
