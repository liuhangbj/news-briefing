#!/usr/bin/env python3
"""
News Briefing v4.2 - 两步筛选全球新闻简报

工作流程:
  第一步 (generate): 生成候选列表 candidates_YYYYMMDD.md
    - 从 FreshRSS 缓存读取24h文章
    - 关键词打分、话题去重
    - 输出 Markdown 候选列表供人工筛选
  
  第二步 (extract): 从缓存提取完整内容生成 filtered_full_YYYYMMDD.md
    - 人工逐条读标题，保存 selected_YYYYMMDD.json（编号列表）
    - 从 freshrss_briefing.json 缓存提取入选文章的完整正文
    - 输出筛选全文数据列表，供生成最终简报

用法:
  python news_briefing.py                    # 第一步：生成候选列表
  python news_briefing.py --mode=extract     # 第二步：提取完整内容
  python news_briefing.py --mode=extract --selected=output/selected_20260610.json
"""

import urllib.request
import ssl
import xml.etree.ElementTree as ET
import json
import os
import time
import hashlib
import re
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime

# ========== 配置 ==========
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
DATA_DIR = f'{PROJECT_DIR}/data'
OUTPUT_DIR = f'{PROJECT_DIR}/output'
CONFIG_DIR = f'{PROJECT_DIR}/config'
LOGS_DIR = f'{PROJECT_DIR}/logs'
CUBOX_API_URL = os.environ.get('CUBOX_API_URL', '')
if not CUBOX_API_URL:
    try:
        env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
        with open(env_path) as f:
            for line in f:
                if line.startswith('CUBOX_API_URL='):
                    CUBOX_API_URL = line.strip().split('=', 1)[1].strip()
                    break
    except Exception:
        pass
if not CUBOX_API_URL:
    CUBOX_API_URL = 'https://cubox.pro/c/api/save/7wbmhrzys6xp7i'




# ========== 关键词分类与加分规则 (v3.2 词组结构) ==========
# 借鉴 TrendRadar 词组机制:keywords(或关系) + required(必须同时命中) + exclude(排除)
# 外部配置文件热更新支持

KEYWORD_CONFIG_FILE = f'{CONFIG_DIR}/keyword_groups.json'
GLOBAL_FILTER_FILE = f'{CONFIG_DIR}/global_filter.json'

# 全局过滤词(命中任意一个直接丢弃)
DEFAULT_GLOBAL_FILTER = [
    '震惊', '太可怕了', '竟然', '刚刚', '重磅', '突发', '揭秘', '曝光',
    '惊呆了', '看完沉默了', '不看后悔', '速看', '紧急', '刷屏',
    '标题党', '广告', '推广', '软文', '培训', '课程', '招聘', '实习',
    '双11', '618', '双十一', '年货节', '大促', '秒杀',
    '网红', '直播带货', '种草', '安利', '薅羊毛',
    '算命', '星座', '塔罗', '风水', '运势',
    '相亲', '彩礼', '出轨', '小三', '离婚', '复合',
    '减肥', '美容', '整形', '医美', '护肤', '祛痘', '美白',
    '养生', '偏方', '秘方', '祖传', '老中医',
    '兼职', '刷单', '返利', '提现', '羊毛', '薅',
]

def load_global_filter():
    """加载全局过滤词"""
    if os.path.exists(GLOBAL_FILTER_FILE):
        try:
            with open(GLOBAL_FILTER_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return DEFAULT_GLOBAL_FILTER

# 词组定义:name=显示名, category=分类, keywords=触发词(或), required=必须词(且), exclude=排除词
DEFAULT_KEYWORD_GROUPS = [
    # === AI / 大模型 ===
    {'name': 'Anthropic/Claude', 'category': '科技',
     'keywords': ['Anthropic', 'Claude', 'Mythos', 'Dario Amodei'],
     'required': ['发布', '推出', '上线', '模型', '产品', '融资', '收入', '估值', '开源', 'API', '安全', '对齐', '宪法'],
     'exclude': ['培训', '课程', '招聘', '实习', '食堂', '办公室', '装修']},
    {'name': 'OpenAI/ChatGPT', 'category': '科技',
     'keywords': ['OpenAI', 'ChatGPT', 'GPT', 'Sora', 'DALL-E', 'Sam Altman', 'Greg Brockman', 'o1', 'o3', 'o4'],
     'required': ['发布', '推出', '上线', '模型', '产品', '融资', '收入', '估值', '开源', 'API', '安全', '对齐'],
     'exclude': ['培训', '课程', '招聘', '实习']},
    {'name': 'DeepSeek', 'category': '科技',
     'keywords': ['DeepSeek', '深度求索', '幻方量化', '梁文锋'],
     'required': [], 'exclude': ['培训', '课程', '招聘']},
    {'name': '国产大模型', 'category': '科技',
     'keywords': ['Qwen', '通义千问', 'MiniMax', 'GLM', '智谱', 'ChatGLM', '文心一言', '讯飞星火', 'Kimi', '月之暗面', '杨植麟'],
     'required': ['发布', '上线', '开源', '模型', '融资', '估值'],
     'exclude': ['使用教程', '入门']},
    {'name': 'AI产业重大信号', 'category': '科技',
     'keywords': ['大模型', '大语言模型', 'LLM', '生成式AI', 'AGI', 'AI模型', 'AI服务', '人工智能', 'AIGC'],
     'required': ['发布', '推出', '上线', '开源', '闭源', '融资', '并购', '估值', 'IPO', '上市', '监管', '立法', '禁令', '制裁'],
     'exclude': ['使用', '教程', '入门', '科普', '介绍', '什么是']},

    # === 芯片 / 半导体 ===
    {'name': '芯片/半导体', 'category': '科技',
     'keywords': ['芯片', '半导体', '光刻机', '光刻胶', '晶圆', '代工', '制程', 'nm', '先进封装', '国产替代', 'EDA', 'IP核'],
     'required': [],
     'exclude': ['使用教程', '入门科普', '什么是', '介绍']},
    {'name': 'GPU/算力', 'category': '科技',
     'keywords': ['GPU', '算力', 'CUDA', 'H100', 'H200', 'B200', 'A100', 'TPU', 'NPU', '智算中心', '超算', '云计算'],
     'required': [],
     'exclude': ['使用教程', '装机', '配置']},
    {'name': '英伟达', 'category': '科技',
     'keywords': ['英伟达', 'NVIDIA', 'GeForce', 'RTX', 'Jensen Huang', '黄仁勋'],
     'required': [], 'exclude': ['显卡评测', '装机', '游戏帧数']},
    {'name': '台积电/代工', 'category': '科技',
     'keywords': ['台积电', 'TSMC', '中芯国际', 'SMIC', '三星代工', 'Intel代工', '格芯', '联电'],
     'required': [], 'exclude': ['财报分析', '股价预测']},

    # === 机器人 / 具身智能 ===
    {'name': '人形机器人', 'category': '科技',
     'keywords': ['人形机器人', '具身智能', '仿生机器人', '双足机器人', '通用人形'],
     'required': [], 'exclude': ['玩具', '遥控']},
    {'name': '工业机器人/机械臂', 'category': '科技',
     'keywords': ['工业机器人', '机械臂', '协作机器人', 'AGV', 'AMR', '无人叉车', '仓储机器人'],
     'required': [], 'exclude': []},
    {'name': '四足/机器狗', 'category': '科技',
     'keywords': ['机器狗', '机械狗', '四足机器人', '机器犬', 'Spot', 'Boston Dynamics'],
     'required': [], 'exclude': ['玩具', '宠物']},
    {'name': '宇树/智元/众擎', 'category': '科技',
     'keywords': ['宇树', 'Unitree', '智元', 'AgiBot', '稚晖君', '彭志辉', '众擎', 'EngineAI', '赵同阳', '王兴兴'],
     'required': [], 'exclude': []},
    {'name': '特斯拉Optimus', 'category': '科技',
     'keywords': ['Optimus', '特斯拉机器人', 'Tesla Bot'],
     'required': [], 'exclude': []},

    # === 科技巨头 ===
    {'name': '华为生态', 'category': '科技',
     'keywords': ['华为', '鸿蒙', 'HarmonyOS', '海思', 'HiSilicon', '昇腾', '鲲鹏', '余承东', '任正非', '孟晚舟'],
     'required': [],
     'exclude': ['华为员工', '华为食堂', '华为面试', '华为校招']},
    {'name': '比亚迪', 'category': '科技',
     'keywords': ['比亚迪', 'BYD', '王传福', '方程豹', '腾势', 'Denza', '仰望', 'Yangwang', '刀片电池', '云辇', '弗迪'],
     'required': [],
     'exclude': ['比亚迪员工', '比亚迪面试', '比亚迪校招']},
    {'name': '字节跳动', 'category': '科技',
     'keywords': ['字节跳动', 'ByteDance', '张一鸣', '梁汝波', '抖音', 'Douyin', 'TikTok', 'Lark', 'CapCut', '剪映', '火山引擎'],
     'required': [],
     'exclude': ['抖音网红', '抖音直播', '抖音教程', '如何使用']},
    {'name': '腾讯', 'category': '科技',
     'keywords': ['腾讯', 'Tencent', '马化腾', '微信', 'WeChat', 'QQ', '天美', '阅文集团', '微众银行', '腾讯云'],
     'required': [], 'exclude': ['微信使用', '微信教程', 'QQ空间']},
    {'name': '大疆', 'category': '科技',
     'keywords': ['大疆', 'DJI', '汪滔', '灵眸', 'Osmo', '如影', 'Ronin', 'RoboMaster', 'Mavic', 'Zenmuse'],
     'required': [], 'exclude': ['评测', '开箱', '教程']},
    {'name': '苹果', 'category': '科技',
     'keywords': ['苹果', 'Apple', 'iPhone', 'iPad', 'MacBook', 'iOS', 'Vision Pro', 'AirPods', 'Tim Cook', '库克', 'M系列芯片'],
     'required': ['发布', '推出', '上市', '销量', '禁令', '制裁', '反垄断', '欧盟', 'App Store'],
     'exclude': ['评测', '开箱', '教程', '使用技巧', 'iPhone拍照']},
    {'name': '谷歌', 'category': '科技',
     'keywords': ['谷歌', 'Google', 'Alphabet', 'Android', 'Chrome', 'YouTube', 'Gemini', 'DeepMind', 'Waymo', '皮查伊', 'Sundar Pichai'],
     'required': ['发布', '推出', '反垄断', '制裁', '禁令', '欧盟', '罚款', '重组', '裁员'],
     'exclude': ['教程', '使用技巧', 'Chrome插件']},
    {'name': '微软', 'category': '科技',
     'keywords': ['微软', 'Microsoft', 'Windows', 'Azure', 'Satya Nadella', 'Copilot', 'OpenAI投资'],
     'required': ['发布', '推出', '反垄断', '重组', '裁员', '收购', '收购动视'],
     'exclude': ['教程', '使用技巧', 'Windows更新']},
    {'name': '亚马逊', 'category': '科技',
     'keywords': ['亚马逊', 'Amazon', 'AWS', '贝索斯', 'Jeff Bezos', 'Andy Jassy'],
     'required': ['收购', '裁员', '反垄断', '云业务'],
     'exclude': ['购物', '快递', 'Prime']},
    {'name': 'Meta', 'category': '科技',
     'keywords': ['Meta', 'Facebook', 'Instagram', 'WhatsApp', '扎克伯格', 'Zuckerberg', '元宇宙', 'VR', 'AR', 'Quest'],
     'required': ['反垄断', '罚款', '重组', '裁员', '元宇宙'],
     'exclude': ['使用', '教程']},
    {'name': '小米/蔚来/理想', 'category': '科技',
     'keywords': ['小米', '雷军', 'Xiaomi', '蔚来', 'NIO', '李斌', '理想', 'Li Auto', '李想', '小鹏', 'XPeng', '何小鹏', '零跑', '哪吒'],
     'required': [],
     'exclude': ['试驾', '评测', '车主', '维权']},

    # === 中东 / 战争 ===
    {'name': '以色列/哈马斯', 'category': '政治',
     'keywords': ['以色列', '哈马斯', '加沙', 'Gaza', 'Hamas', 'IDF', '内塔尼亚胡', 'Netanyahu', '巴勒斯坦', '杰哈德', 'PIJ'],
     'required': [], 'exclude': ['旅游', '美食', '文化', '历史']},
    {'name': '伊朗/核问题', 'category': '政治',
     'keywords': ['伊朗', 'Iran', '核设施', '铀浓缩', '离心机', '伊核协议', 'JCPOA', '什叶派', '革命卫队', 'IRGC'],
     'required': [], 'exclude': ['旅游', '美食', '波斯', '历史']},
    {'name': '也门/胡塞', 'category': '政治',
     'keywords': ['也门', 'Yemen', '胡塞', 'Houthi', '胡塞武装', '红海', '曼德海峡'],
     'required': [], 'exclude': ['旅游']},
    {'name': '黎巴嫩/真主党', 'category': '政治',
     'keywords': ['黎巴嫩', 'Lebanon', '真主党', 'Hezbollah', '贝鲁特', 'Beirut'],
     'required': [], 'exclude': ['美食', '旅游']},
    {'name': '霍尔木兹/波斯湾', 'category': '政治',
     'keywords': ['霍尔木兹', 'Hormuz', '波斯湾', 'Persian Gulf', '阿曼湾', '海峡'],
     'required': [], 'exclude': ['旅游']},
    {'name': '中东战争', 'category': '政治',
     'keywords': ['中东', 'Middle East', '战争', '空袭', '轰炸', '导弹', '报复', '停火', '和谈', '调解', '斡旋'],
     'required': ['战争', '冲突', '空袭', '轰炸', '导弹', '伤亡', '制裁', '石油', '油价'],
     'exclude': ['旅游', '美食', '文化', '历史', '投资', '商机']},

    # === 台海 ===
    {'name': '台海/台湾', 'category': '政治',
     'keywords': ['台湾', '台海', 'Taiwan', '海峡', '解放军', '军演', '绕台', '台军', '对台', '武统', '和统', '统一', '台独', '赖清德', '蔡英文', '国民党', '民进党'],
     'required': [],
     'exclude': ['台湾电影', '台湾美食', '台湾旅游', '台湾歌手', '台湾艺人', '台剧', '金马奖']},

    # === 朝鲜 ===
    {'name': '朝鲜/核武器', 'category': '政治',
     'keywords': ['朝鲜', 'North Korea', '金正恩', 'Kim Jong', '核武', '核武器', '核试验', '导弹', '洲际导弹', '弹道导弹', '潜射', 'SLBM', 'KN-', '火星炮'],
     'required': [], 'exclude': ['旅游', '脱北者', '韩剧']},

    # === 俄乌 ===
    {'name': '俄乌战争', 'category': '政治',
     'keywords': ['俄乌', 'Russia', 'Ukraine', '乌克兰', '俄罗斯', '普京', 'Putin', '泽连斯基', 'Zelensky', '北约', 'NATO', '欧盟制裁', '欧盟', 'EU', 'G7', 'G20'],
     'required': [],
     'exclude': ['俄罗斯旅游', '乌克兰旅游', '俄罗斯文化', '世界杯']},
    {'name': '战争/冲突', 'category': '政治',
     'keywords': ['战争', '冲突', '空袭', '轰炸', '导弹', '报复打击', '军事基地', '美军', '伤亡', '阵亡', '战俘', '难民', '人道主义危机'],
     'required': [],
     'exclude': ['电影', '游戏', '小说', '历史']},

    # === 外交 ===
    {'name': '中国外交', 'category': '政治',
     'keywords': ['王毅', '外交部', '外交部长', '国务委员', '习近平', '李克强', '李强', '中国外交', '中美对话', '中俄', '中欧', '一带一路', 'BRI', '上合组织', 'SCO', '金砖', 'BRICS'],
     'required': [],
     'exclude': ['习近平思想', '习近平语录']},
    {'name': '美国外交', 'category': '政治',
     'keywords': ['鲁比奥', 'Rubio', '布林肯', 'Blinken', '国务卿', '美国国务院', '大使', 'embassy', '领事馆'],
     'required': [], 'exclude': []},
    {'name': '其他外交', 'category': '政治',
     'keywords': ['巴基斯坦', 'Kenya', '肯尼亚', 'Uruguay', '乌拉圭', '巴西', 'Brazil', '南非', 'South Africa', '沙特', 'Saudi', '阿联酋', 'UAE', '土耳其', 'Turkey', '埃及', 'Egypt'],
     'required': ['访问', '会见', '会谈', '签约', '援助', '制裁', '断交', '建交', '战略合作'],
     'exclude': ['旅游', '留学', '移民']},

    # === 能源 / 矿业 ===
    {'name': '锂矿', 'category': '财经',
     'keywords': ['锂矿', '锂辉石', '锂云母', '盐湖提锂', '碳酸锂', '氢氧化锂', 'Lithium', 'SQM', '雅保', 'Albemarle', '天齐锂业', '赣锋锂业'],
     'required': [],
     'exclude': ['电动汽车', '电池', '储能']},
    {'name': '铜矿', 'category': '财经',
     'keywords': ['铜矿', '铜价', '铜精矿', '铜冶炼', 'LME铜', 'COMEX铜', '智利铜', '秘鲁铜', 'Codelco', 'Freeport'],
     'required': [], 'exclude': []},
    {'name': '镍/钴', 'category': '财经',
     'keywords': ['镍', 'Nickel', '钴', 'Cobalt', '镍矿', '钴矿', '红土镍矿', 'MHP', '高冰镍', '青山控股', '华友钴业'],
     'required': [], 'exclude': []},
    {'name': '稀土', 'category': '财经',
     'keywords': ['稀土', 'Rare Earth', '镧', '铈', '钕', '镨', '钐', '镝', '铽', '北方稀土', '中国稀土', '稀土出口', '稀土管制'],
     'required': [], 'exclude': []},
    {'name': '石油/天然气', 'category': '财经',
     'keywords': ['石油', '原油', '天然气', '页岩气', 'OPEC', '欧佩克', '沙特阿美', 'Aramco', 'BP', 'Shell', 'Exxon', '雪佛龙', 'Chevron', '油价', '气价', '布伦特', 'Brent', 'WTI'],
     'required': [],
     'exclude': ['加油站', '油价调整', '国内油价']},
    {'name': '煤炭', 'category': '财经',
     'keywords': ['煤炭', '动力煤', '焦煤', '焦炭', '煤化工', '煤制油', '煤矿', '山西煤炭', '内蒙古煤炭', '澳洲煤炭'],
     'required': [], 'exclude': ['煤炭使用', '煤炭科普']},
    {'name': '能源战略', 'category': '财经',
     'keywords': ['能源', '能源安全', '能源战略', '能源转型', '能源独立', '能源危机', '电力短缺', '缺电', '停电', '电网', '特高压', '智能电网'],
     'required': [],
     'exclude': ['家庭用电', '节电', '电费']},
    {'name': '光伏/太阳能', 'category': '科技',
     'keywords': ['光伏', '太阳能', 'PERC', 'TOPCon', 'HJT', '钙钛矿', '逆变器', '隆基', '通威', '晶科', '天合', '晶澳'],
     'required': [], 'exclude': ['家庭光伏', '屋顶光伏', '安装']},
    {'name': '核能', 'category': '科技',
     'keywords': ['核能', '核电', '核反应堆', 'SMR', '小型模块化反应堆', '核聚变', 'ITER', '可控核聚变', '核废料', '铀', 'Uranium'],
     'required': [], 'exclude': ['核医学', '核磁共振']},
    {'name': '水电', 'category': '科技',
     'keywords': ['水电', '水电站', '大坝', '三峡', '白鹤滩', '溪洛渡', '雅鲁藏布江', '水电开发'],
     'required': [], 'exclude': ['旅游', '风景']},
    {'name': '黄金/贵金属', 'category': '财经',
     'keywords': ['黄金', 'Gold', '白银', 'Silver', '贵金属', 'COMEX黄金', '伦敦金', '金条', '金币', '央行购金'],
     'required': ['价格', '涨跌', '暴涨', '暴跌', '创历史新高', '储备', '央行'],
     'exclude': ['首饰', '饰品', '金店', '结婚']},

    # === 宏观经济 ===
    {'name': '美联储/利率', 'category': '财经',
     'keywords': ['美联储', 'Fed', '加息', '降息', '利率', '联邦基金利率', 'FOMC', '鲍威尔', 'Powell', '耶伦', 'Yellen', '缩表', '量化宽松', 'QE', 'QT'],
     'required': [], 'exclude': ['美联储历史', '美联储是什么']},
    {'name': '通胀/物价', 'category': '财经',
     'keywords': ['通胀', '通货膨胀', 'CPI', 'PPI', '核心CPI', '物价', '物价上涨', '生活成本', '食品价格'],
     'required': [], 'exclude': []},
    {'name': 'GDP/经济', 'category': '财经',
     'keywords': ['GDP', '经济增长', '经济衰退', 'Recession', 'GDP增速', '季度GDP', '年报', 'IMF', '国际货币基金组织', '世界银行', 'World Bank'],
     'required': [], 'exclude': ['GDP是什么', 'GDP计算']},
    {'name': '就业/失业', 'category': '财经',
     'keywords': ['就业', '失业', '失业率', '非农就业', 'NFP', '非农数据', '劳动力市场', '裁员', 'layoff', '岗位', '招聘', '降薪'],
     'required': [],
     'exclude': ['求职技巧', '简历', '面试']},
    {'name': '贸易/关税', 'category': '财经',
     'keywords': ['贸易', '关税', 'Tariff', '贸易战', '贸易摩擦', '反倾销', '反补贴', 'WTO', '出口管制', '技术封锁', '脱钩', 'decoupling', '供应链', 'supply chain'],
     'required': [], 'exclude': ['跨境电商', '海淘']},
    {'name': '汇率/货币', 'category': '财经',
     'keywords': ['汇率', '人民币', '美元', '欧元', '日元', '英镑', '贬值', '升值', '外汇储备', 'FX', 'Forex', '离岸人民币', 'CNH', '美元指数', 'DXY'],
     'required': [],
     'exclude': ['换汇', '留学换汇', '旅游']},
    {'name': '比特币/加密货币', 'category': '财经',
     'keywords': ['比特币', 'Bitcoin', '以太坊', 'Ethereum', '加密货币', 'cryptocurrency', '数字货币', '区块链', 'Blockchain', '稳定币', 'Stablecoin', 'CBDC', '央行数字货币', 'DeFi', 'NFT'],
     'required': [],
     'exclude': ['NFT艺术', 'NFT头像', '加密货币入门']},
    {'name': '房地产/基建', 'category': '财经',
     'keywords': ['房地产', '房价', '楼市', '土地', '基建', '投资', '融资', 'IPO', '上市', '并购', '破产', '债务', '城投债', '地方债', '房地产泡沫', '恒大', '碧桂园', '万科'],
     'required': [],
     'exclude': ['买房攻略', '装修', '租房']},

    # === 网络安全 ===
    {'name': '数据泄露', 'category': '科技',
     'keywords': ['数据泄露', '数据泄漏', '信息泄露', '用户信息', '数据库泄露', '百万用户', '千万用户', '亿用户'],
     'required': [], 'exclude': []},
    {'name': '黑客/勒索', 'category': '科技',
     'keywords': ['黑客', '勒索软件', 'Ransomware', '勒索病毒', '勒索攻击', '网络攻击', 'DDoS', '钓鱼', 'Phishing', '恶意软件', 'Malware', '木马', 'APT', '高级持续性威胁'],
     'required': [], 'exclude': ['黑客教程', '黑客技术入门']},
    {'name': '零日/漏洞', 'category': '科技',
     'keywords': ['零日漏洞', 'Zero-day', 'CVE-', '漏洞', 'Vulnerability', '安全补丁', '紧急修复', '远程代码执行', 'RCE'],
     'required': [], 'exclude': ['漏洞赏金', '漏洞挖掘教程']},
    {'name': 'CISA/国土安全', 'category': '科技',
     'keywords': ['CISA', '国土安全部', '网络安全局', 'NSA', 'GCHQ', '国家漏洞库', 'CNVD', '关键基础设施', '关基'],
     'required': [], 'exclude': []},

    # === 航天 ===
    {'name': 'SpaceX/星舰', 'category': '科技',
     'keywords': ['SpaceX', '星舰', 'Starship', '星链', 'Starlink', '猎鹰', 'Falcon', '马斯克', 'Musk', '火星', 'Mars', '载人登月', '月球基地'],
     'required': [],
     'exclude': ['SpaceX粉丝', '马斯克语录']},
    {'name': '中国航天', 'category': '科技',
     'keywords': ['中国航天', '长征', '神舟', '天宫', '空间站', '嫦娥', '玉兔', '祝融', '北斗', '北斗导航', '火箭军', '商业航天', '卫星互联网'],
     'required': [], 'exclude': ['航天科普']},
    {'name': '商业航天', 'category': '科技',
     'keywords': ['商业航天', '卫星互联网', '低轨卫星', 'LEO', '卫星星座', 'Starlink竞品', 'OneWeb', '蓝色起源', 'Blue Origin', '维珍银河', 'Virgin Galactic'],
     'required': [], 'exclude': []},

    # === 前沿科技 ===
    {'name': '量子计算', 'category': '科技',
     'keywords': ['量子', '量子计算', '量子通信', '量子密钥', 'QKD', '量子霸权', 'Quantum Supremacy', '超导量子', '离子阱', '光量子'],
     'required': [], 'exclude': ['量子力学', '量子科普', '量子养生']},
    {'name': '脑机接口', 'category': '科技',
     'keywords': ['脑机接口', 'BCI', 'Neuralink', '马斯克脑机', '脑芯片', '脑电波', '意念控制', '缸中之脑'],
     'required': [], 'exclude': ['科幻', '小说']},
    {'name': '基因编辑', 'category': '科技',
     'keywords': ['基因编辑', 'CRISPR', '基因治疗', 'Gene Therapy', '遗传病', '罕见病', 'mRNA', '疫苗', 'FDA批准', '临床试验'],
     'required': [], 'exclude': ['基因科普', '基因检测']},

    # === 公共卫生 ===
    {'name': '疫情/传染病', 'category': '社会',
     'keywords': ['疫情', '传染病', '大流行', 'Pandemic', '世卫组织', 'WHO', '疾控中心', 'CDC', '封控', '隔离', '核酸检测', '疫苗接种'],
     'required': [],
     'exclude': ['历史疫情', '疫情科普']},
    {'name': '埃博拉/特殊疫情', 'category': '社会',
     'keywords': ['埃博拉', 'Ebola', '猴痘', 'Mpox', '霍乱', 'Cholera', '马尔堡', 'Marburg', '出血热', '炭疽'],
     'required': [], 'exclude': []},
    {'name': '医保/药品', 'category': '社会',
     'keywords': ['医保', '国家医保', '药品目录', '集采', '医保谈判', 'DRG', 'DIP', '医保基金', '医保报销', '跨省就医'],
     'required': [], 'exclude': ['医保使用', '医保科普']},
    {'name': '食品安全', 'category': '社会',
     'keywords': ['食品安全', '兽药残留', '农药残留', '抗生素超标', '重金属', '添加剂', '召回', '食物中毒', '抽检不合格'],
     'required': [], 'exclude': ['食品安全科普']},

    # === 社会民生 ===
    {'name': '就业/青年', 'category': '社会',
     'keywords': ['就业', '失业', '青年就业', '毕业生', '大学生就业', '招聘', '裁员', '降薪', '灵活就业', '零工经济', 'Gig Economy'],
     'required': [],
     'exclude': ['求职技巧', '简历模板', '面试']},
    {'name': '人口/生育', 'category': '社会',
     'keywords': ['人口', '老龄化', '出生率', '生育', '生育率', '养老金', '延迟退休', '社保', '三孩', '二胎', '独生子女'],
     'required': [], 'exclude': ['养老护理', '养老旅游']},
    {'name': '教育/学术', 'category': '社会',
     'keywords': ['教育', '高考', '大学', '学术', '论文', '诺贝尔奖', 'Nobel Prize', '科研', '基础研究', '国自然', 'NSFC', '学术不端'],
     'required': [],
     'exclude': ['高考志愿', '留学', '考研', '学习方法']},
    {'name': '气候/环境', 'category': '社会',
     'keywords': ['极端气候', '高温', '热浪', '干旱', '洪水', '台风', '地震', '灾难', '全球变暖', '气候危机', 'Climate Crisis', '碳中和', '碳达峰', '双碳'],
     'required': [],
     'exclude': ['天气预报', '气候科普']},
    {'name': '灾难/事故', 'category': '社会',
     'keywords': ['交通事故', '火灾', '爆炸', '矿难', '坍塌', '沉船', '空难', '坠机', '地震', '海啸', '泥石流', '救援', '伤亡'],
     'required': [], 'exclude': ['电影', '小说']},

    # === 文化IP ===
    {'name': '黑神话/游戏', 'category': '文化',
     'keywords': ['黑神话', '悟空', '冯骥', '游戏科学', '影之刃零', '梁其伟', '国产3A', '游戏工业化'],
     'required': [], 'exclude': ['游戏攻略', '游戏评测', 'Steam打折']},
    {'name': '三体/科幻IP', 'category': '文化',
     'keywords': ['三体', '刘慈欣', '流浪地球', '郭帆', '科幻', 'Science Fiction', '雨果奖', 'Hugo Award'],
     'required': [],
     'exclude': ['科幻小说推荐', '科幻电影排行']},
    {'name': '申奥/体育', 'category': '文化',
     'keywords': ['申奥', '奥运会', 'Olympics', 'IOC', '亚运', '大运', '世界杯', 'FIFA', '电竞', 'Esports', '入奥'],
     'required': [],
     'exclude': ['比赛结果', '比分', '夺冠', '金牌', '运动员']},

    # === 零售/消费 ===
    {'name': '胖东来', 'category': '财经',
     'keywords': ['胖东来', '于东来', '许昌', '新乡'],
     'required': [], 'exclude': ['胖东来攻略', '胖东来打卡']},

    {'name': '银行危机', 'category': '财经',
     'keywords': ['银行危机', '银行倒闭', 'Bank Run', '挤兑', '系统性风险', '雷曼', '硅谷银行', 'SVB', '瑞信', 'Credit Suisse', '金融稳定', 'FSB'],
     'required': [],
     'exclude': ['银行历史']},
    {'name': '金融监管', 'category': '财经',
     'keywords': ['金融监管', '巴塞尔协议', 'Basel', '资本充足率', '杠杆率', '影子银行', 'P2P', '金融犯罪', '洗钱', '反洗钱', 'AML'],
     'required': [],
     'exclude': []},
    {'name': '保险', 'category': '财经',
     'keywords': ['保险', '保险公司', '偿付能力', '保险监管', '再保险', '巨灾保险', '养老保险', '健康险'],
     'required': [],
     'exclude': ['保险科普', '买保险']},
    {'name': '重大案件', 'category': '社会',
     'keywords': ['最高法院', '最高人民法院', '终审', '判决', '死刑', '无罪释放', '冤案', '平反', '再审', '引渡', '国际刑警', '红色通缉令'],
     'required': [],
     'exclude': ['电视剧', '小说']},
    {'name': '立法/修法', 'category': '社会',
     'keywords': ['立法', '修法', '新法', '法律草案', '人大', '常委会', '法律修订', '刑法修正案', '民法典', '宪法', '司法解释'],
     'required': [],
     'exclude': ['法律科普', '法学院']},
    {'name': '航空事故', 'category': '社会',
     'keywords': ['空难', '坠机', '飞机失事', '航空事故', 'MH370', '波音', 'Boeing', '空客', 'Airbus', 'FAA', '停飞', '航空安全'],
     'required': [],
     'exclude': ['航空展', '航空科普']},
    {'name': '交通/基建', 'category': '财经',
     'keywords': ['高铁', '铁路', '地铁', '港口', '航运', '物流', '供应链中断', '集装箱', '运价', '货运', '中欧班列', '一带一路运输'],
     'required': [],
     'exclude': ['旅游攻略', '交通指南']},
    {'name': '粮食安全', 'category': '财经',
     'keywords': ['粮食安全', '饥荒', '粮食危机', '小麦', '玉米', '大豆', '稻米', '产量', '丰收', '歉收', '粮食储备', '粮食进口', '粮食出口', '黑海粮食', '粮仓'],
     'required': [],
     'exclude': ['粮食科普', '美食']},
    {'name': '农业政策', 'category': '财经',
     'keywords': ['农业', '三农', '乡村振兴', '农村', '耕地', '耕地红线', '土地承包', '农机', '化肥', '农药', '种子', '种业', '转基因', '杂交水稻'],
     'required': [],
     'exclude': ['农业旅游', '农家乐']},
    {'name': '消费/零售', 'category': '财经',
     'keywords': ['消费', '零售', '社零', '消费降级', '消费升级', '消费复苏', '内需', 'CPI消费', '免税', 'Costco', '山姆', '会员店', '便利店', '新零售', '社区团购'],
     'required': [],
     'exclude': ['消费指南', '购物攻略']},
    {'name': '电商/平台', 'category': '财经',
     'keywords': ['电商', '淘宝', '京东', '拼多多', 'Temu', 'Shein', '亚马逊电商', '直播电商', '跨境电商', '出海', '海外仓', '独立站', 'SHEIN', '速卖通'],
     'required': [],
     'exclude': ['电商教程', '开店']},
    {'name': '5G/6G/通信', 'category': '科技',
     'keywords': ['5G', '6G', '通信', '基站', '频谱', '华为5G', '爱立信', 'Ericsson', '诺基亚', 'Nokia', '高通', 'Qualcomm', '调制解调器', '毫米波', '卫星通信', '低轨卫星互联网'],
     'required': [],
     'exclude': ['5G套餐', '手机信号']},
    {'name': '互联网/平台', 'category': '科技',
     'keywords': ['互联网', '平台经济', '平台反垄断', '反垄断', '滴滴', '美团', '饿了么', '携程', '网约车', '共享单车', '平台监管', 'APP整改', '工信部通报'],
     'required': [],
     'exclude': ['APP推荐', '软件教程']},
    {'name': '新材料', 'category': '科技',
     'keywords': ['新材料', '石墨烯', '碳纤维', '超导', '高温合金', '复合材料', '纳米材料', '生物材料', '3D打印材料', '增材制造'],
     'required': [],
     'exclude': ['材料科普']},
    {'name': '化工/危化', 'category': '社会',
     'keywords': ['化工', '化工事故', '爆炸', '化工厂', '有毒', '泄漏', '污染', '危化品', 'PX', '乙烯', '炼化', '石化', 'BP', '陶氏', '杜邦'],
     'required': [],
     'exclude': ['化工科普', '化工专业']},
    {'name': '军事装备', 'category': '政治',
     'keywords': ['航母', '驱逐舰', '护卫舰', '核潜艇', 'F-35', '歼-20', 'J-20', '东风导弹', '高超音速', 'Hypersonic', '雷达', '电子战', '无人机军事', '军售', '军贸', 'NATO军演'],
     'required': [],
     'exclude': ['军事模型', '军事游戏']},
    {'name': '国防预算', 'category': '政治',
     'keywords': ['国防预算', '军费', '军事开支', '国防开支', '北约军费', 'NATO军费', '2%GDP', '军工复合体'],
     'required': [],
     'exclude': []},
    {'name': '生态环境', 'category': '社会',
     'keywords': ['物种灭绝', '生物多样性', '濒危物种', '自然保护区', '湿地', '珊瑚礁', '森林砍伐', '亚马逊雨林', '生态灾难', '漏油', '海洋污染', '塑料污染', '微塑料'],
     'required': [],
     'exclude': ['动物世界', '纪录片']},
    {'name': 'ESG/绿色金融', 'category': '财经',
     'keywords': ['ESG', '绿色金融', '绿色债券', '碳交易', '碳市场', '碳税', 'CBAM', '碳边境', '欧盟碳关税', 'Scope 3', 'TCFD', 'ISSB', '可持续发展'],
     'required': [],
     'exclude': ['ESG入门']},
    {'name': '重大体育赛事', 'category': '文化',
     'keywords': ['奥运会', 'Olympics', 'IOC', '世界杯', 'FIFA World Cup', '亚运会', '大运会', '全运会', '申办', '电竞入奥', '电竞入亚', 'WADA', '反兴奋剂'],
     'required': [],
     'exclude': ['比赛结果', '比分', 'NBA', 'CBA', '中超', '英超']},
    {'name': '宗教/民族', 'category': '社会',
     'keywords': ['宗教冲突', '民族冲突', '教派冲突', '极端主义', '恐怖主义', '恐袭', 'ISIS', '基地组织', 'Al-Qaeda', '塔利班', 'Taliban', '反恐', '圣战', 'Jihad'],
     'required': [],
     'exclude': ['宗教文化', '宗教旅游']},
    {'name': 'AI治理/伦理', 'category': '科技',
     'keywords': ['AI治理', 'AI伦理', '算法歧视', '算法推荐', '深度伪造', 'Deepfake', 'AI监管', 'AI立法', '布鲁塞尔效应', '欧盟AI法案', 'EU AI Act', '数据隐私', 'GDPR', '个人信息保护法', 'PIPL'],
     'required': [],
     'exclude': ['AI科普']},
    {'name': '移民/难民', 'category': '社会',
     'keywords': ['移民', '难民', '边境危机', '非法移民', '遣返', '绿卡', 'H-1B', '签证政策', '边境墙', '美墨边境', '地中海难民', '偷渡', '人口贩运'],
     'required': [],
     'exclude': ['移民留学', '移民攻略']},
    {'name': '重大犯罪', 'category': '社会',
     'keywords': ['扫黑', '除恶', '扫黑除恶', '有组织犯罪', '毒品', '贩毒', '禁毒', '金三角', '缅北', '电诈', '电信诈骗', '网络诈骗', '杀猪盘', '缅北诈骗', '跨境犯罪'],
     'required': [],
     'exclude': ['犯罪小说', '刑侦剧']},
    {'name': '执法/司法', 'category': '社会',
     'keywords': ['执法', '抓捕', '通缉', '国际刑警', 'Interpol', '引渡', '引渡条约', '红色通缉令', '反腐败', 'FCPA', '海外反腐败', '透明国际', 'TI', '清廉指数'],
     'required': [],
     'exclude': ['美剧', '小说']},
    {'name': '医改/医疗', 'category': '社会',
     'keywords': ['医改', '医疗改革', '公立医院', '私立医院', '分级诊疗', '医联体', '远程医疗', '互联网医疗', '医疗事故', '医患纠纷', '医生待遇', '护士', '执业医师'],
     'required': [],
     'exclude': ['养生', '健康科普']},
    {'name': '教育政策', 'category': '社会',
     'keywords': ['双减', '教培', '教育培训', '校外培训', 'K12', '职业教育', '职高', '普职分流', '留学政策', '留学生', '海归', 'STEM教育', '科学教育', '课后服务', '教育公平'],
     'required': [],
     'exclude': ['学习方法', '考试技巧']},
    {'name': '房地产政策', 'category': '财经',
     'keywords': ['保交楼', '烂尾楼', '预售制', '现房销售', '房产税', '房地产税', '限购', '限售', '限贷', '公积金', '房住不炒', '共有产权房', '保障房', '廉租房', 'REITs', '城市更新', '旧改'],
     'required': [],
     'exclude': ['买房攻略', '装修']},
    {'name': '旅游/出入境', 'category': '社会',
     'keywords': ['免签', '签证', '出入境', '护照', '国门开放', '边境开放', '旅游复苏', '出境游', '入境游', '邮轮', '邮轮业', '航空业恢复', '航班恢复', '国际航线'],
     'required': [],
     'exclude': ['旅游攻略', '景点推荐']},
    {'name': '电竞产业', 'category': '文化',
     'keywords': ['电竞', 'Esports', '英雄联盟', 'LOL', '王者荣耀', 'DOTA', 'CS:GO', 'Valve', '拳头', 'Riot', '电竞赛事', '电竞入亚', '电竞产业', '游戏直播', 'Twitch', '虎牙', '斗鱼'],
     'required': [],
     'exclude': ['游戏攻略', '游戏评测']},
    {'name': '联合国/国际组织', 'category': '政治',
     'keywords': ['联合国', 'UN', '安理会', 'UNSC', '决议', '维和行动', 'UN Peacekeeping', '教科文组织', 'UNESCO', '人权理事会', '国际法院', 'ICJ', '海牙', 'WTO争端', '国际仲裁', 'PCA', '南海仲裁'],
     'required': [],
     'exclude': ['联合国历史', 'UN实习']},
    {'name': '国际气候/环境协议', 'category': '社会',
     'keywords': ['巴黎协定', 'Paris Agreement', 'COP', '气候大会', 'IPCC', '气候谈判', '气候融资', '损失与损害', 'Loss and Damage', '气候赔偿', '绿色气候基金', 'GCF'],
     'required': [],
     'exclude': ['气候科普']},
    {'name': '南海/东海', 'category': '政治',
     'keywords': ['南海', 'South China Sea', '九段线', '岛礁', '填海', '南海仲裁', '航行自由', 'FONOP', '东海', '钓鱼岛', '尖阁诸岛', 'Senkaku', '专属经济区', 'EEZ', '大陆架'],
     'required': [],
     'exclude': ['南海旅游']},
    {'name': '水资源/干旱', 'category': '社会',
     'keywords': ['干旱', '旱灾', '缺水', '水资源', '尼罗河', '湄公河', '亚马逊河', '大坝', '水电站', '蓄水', '引水', '地下水', '超采', '水位下降', '鄱阳湖', '洞庭湖'],
     'required': [],
     'exclude': ['旅游']},
    {'name': '制造业/PMI', 'category': '财经',
     'keywords': ['制造业', 'PMI', '工业', '工业增加值', '工厂', '生产线', '产业转移', '回流', 'Reshoring', '近岸外包', 'Nearshoring', '友岸外包', 'Friendshoring', '越南制造', '印度制造', '墨西哥制造'],
     'required': [],
     'exclude': ['制造业科普']},
    {'name': '汽车产业', 'category': '财经',
     'keywords': ['汽车', '汽车销量', '汽车市场', '新能源汽车', 'EV', '插电混动', 'PHEV', '增程式', '混动', '燃油车', 'ICE', '汽车出口', '汽车进口', '关税', '汽车业', '丰田', '大众', 'BBA', '奔驰', '宝马', '奥迪'],
     'required': [],
     'exclude': ['汽车评测', '买车', '试驾']},
    {'name': '医药产业', 'category': '科技',
     'keywords': ['医药', '制药', '药企', '辉瑞', 'Pfizer', '默沙东', 'MSD', '强生', 'J&J', '诺华', 'Novartis', '罗氏', 'Roche', '阿斯利康', 'AstraZeneca', '恒瑞', '百济神州', '创新药', '仿制药', '集采', '医保谈判'],
     'required': [],
     'exclude': ['医药科普', '用药']},
    {'name': '生物技术', 'category': '科技',
     'keywords': ['生物技术', '合成生物学', 'SynBio', '生物制造', '发酵', '细胞培养肉', '人造肉', 'Lab-grown meat', '生物燃料', '生物柴油', '酶', '催化剂', '工业生物'],
     'required': [],
     'exclude': ['生物技术科普']},
]

def log(msg):
    ts = datetime.now().strftime('%H:%M:%S')
    line = f"[{ts}] {msg}"
    print(line)
    log_path = f'{LOGS_DIR}/news_briefing.log'
    os.makedirs(LOGS_DIR, exist_ok=True)
    with open(log_path, 'a', encoding='utf-8') as f:
        f.write(line + '\n')

def load_keyword_groups():
    """加载关键词词组,支持外部配置文件热更新"""
    if os.path.exists(KEYWORD_CONFIG_FILE):
        try:
            with open(KEYWORD_CONFIG_FILE, 'r', encoding='utf-8') as f:
                ext = json.load(f)
            if isinstance(ext, list) and len(ext) > 0:
                # 验证格式
                valid = []
                for item in ext:
                    if isinstance(item, dict) and 'name' in item and 'category' in item and 'keywords' in item:
                        valid.append(item)
                if valid:
                    log(f"[keyword] 加载外部词组: {KEYWORD_CONFIG_FILE}, {len(valid)} 组")
                    return valid
        except Exception as e:
            log(f"[keyword] 外部配置加载失败: {e}, 使用内置词组")
    return DEFAULT_KEYWORD_GROUPS

# 全局关键词词组(运行时加载)
KEYWORD_GROUPS = load_keyword_groups()
# 全局过滤词(运行时加载)
GLOBAL_FILTER = load_global_filter()


# ========== 话题级去重配置 ==========
STOPWORDS = set([
    '的', '了', '在', '是', '我', '有', '和', '就', '不', '人', '都', '一', '一个', '上', '也', '很', '到', '说',
    '要', '去', '你', '会', '着', '没有', '看', '好', '自己', '这', '那', '为', '之', '与', '及', '等', '将',
    '对', '年', '月', '日', '中', '新', '大', '小', '高', '低', '多', '少', '来', '过', '下', '能', '可以',
    '还是', '就是', '还', '而', '但', '并', '从', '以', '被', '把', '让', '给', '向', '往', '于', '关于',
    '对于', '由于', '因为', '所以', '因此', '如果', '即使', '虽然', '尽管', '不但', '而且', '或者', '要么',
    '假如', '譬如', '比如', '像', '似乎', '一样', '一般', '通常', '常常', '经常', '往往', '一直', '总是',
    '千万', '万一', '一概', '一律', 'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
    'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'shall', 'should', 'may', 'might',
    'can', 'could', 'must', 'ought', 'need', 'dare', 'used', 'to', 'of', 'in', 'for', 'on', 'with',
    'at', 'by', 'from', 'as', 'into', 'through', 'during', 'before', 'after', 'above', 'below',
    'between', 'under', 'and', 'but', 'or', 'yet', 'so', 'if', 'because', 'although', 'though',
    'while', 'where', 'when', 'that', 'which', 'who', 'whom', 'whose', 'what', 'this', 'these',
    'those', 'i', 'you', 'he', 'she', 'it', 'we', 'they', 'me', 'him', 'her', 'us', 'them',
    'my', 'your', 'his', 'its', 'our', 'their', 'mine', 'yours', 'hers', 'ours', 'theirs',
    'myself', 'yourself', 'himself', 'herself', 'itself', 'ourselves', 'yourselves', 'themselves',
])

SIMILARITY_THRESHOLD = 0.35  # 话题相似度阈值

# ========== 工具函数 ==========

def load_json(f, default=None):
    try:
        if os.path.exists(f):
            with open(f, 'r', encoding='utf-8') as fp:
                return json.load(fp)
    except Exception:
        pass
    return default if default is not None else {}

def save_json(f, data):
    with open(f, 'w', encoding='utf-8') as fp:
        json.dump(data, fp, ensure_ascii=False, indent=2)

def article_hash(title, url):
    return hashlib.md5(f"{title}:{url}".encode()).hexdigest()[:16]

def parse_pub_date(pub_date_str):
    """解析 RSS/Atom 各种日期格式,返回 datetime 或 None"""
    if not pub_date_str:
        return None
    s = pub_date_str.strip()
    formats = [
        '%a, %d %b %Y %H:%M:%S %z',
        '%a, %d %b %Y %H:%M:%S %Z',
        '%Y-%m-%dT%H:%M:%S%z',
        '%Y-%m-%dT%H:%M:%S',
        '%Y-%m-%d %H:%M:%S',
        '%d %b %Y %H:%M:%S %z',
    ]
    for fmt in formats:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    try:
        return parsedate_to_datetime(s)
    except Exception:
        pass
    return None


def clean_desc(text, max_len=2000):
    """清理摘要,去除噪音前缀,限制长度"""
    if not text:
        return ''
    text = re.sub(r'<[^>]+>', '', text)
    text = text.replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')
    text = text.replace('\n', ' ').replace('\r', ' ')
    text = text.strip()
    noise_patterns = [
        r'(?:本文来自)?微信公众号[:：]?\s*\S+\s*[,，]\s*作者[:：]\s*\S+\s*',
        r'本文来自[^,，]+[,，]\s*作者[:：]\s*\S+\s*',
        r'作者[:：]\s*\S+\s*',
        r'编辑[:：]\s*\S+\s*',
        r'图片来源[:：]\s*\S+\s*',
        r'原标题[:：]\s*\S+\s*',
        r'来源[:：]\s*\S+\s*',
    ]
    for pattern in noise_patterns:
        text = re.sub(pattern, '', text, count=1)
    text = text.strip()
    if len(text) > max_len:
        text = text[:max_len-3] + '...'
    return text

# ========== 话题级去重 ==========

def topic_key(title):
    """提取标题的话题关键词集合"""
    # 统一小写/中文,去掉标点数字
    cleaned = re.sub(r'[^\u4e00-\u9fff\w]', ' ', title.lower())
    words = set()
    for w in cleaned.split():
        w = w.strip()
        if not w or w in STOPWORDS:
            continue
        if w.isdigit():
            continue
        if '\u4e00' <= w[0] <= '\u9fff':
            # 中文:逐字拆分,去掉单字停用词
            for ch in w:
                if ch not in STOPWORDS and not ch.isdigit():
                    words.add(ch)
        else:
            # 英文:保留3字母以上
            if len(w) >= 3:
                words.add(w)
    return words

def is_similar_topic(t1, t2, threshold=SIMILARITY_THRESHOLD):
    """判断两个标题是否属于同一话题"""
    k1 = topic_key(t1)
    k2 = topic_key(t2)
    if not k1 or not k2:
        return False
    intersection = len(k1 & k2)
    union = len(k1 | k2)
    if union == 0:
        return False
    return intersection >= 3 and intersection / union >= threshold



# ========== 去重管理 ==========

SEEN_FILE = f'{DATA_DIR}/seen.json'

def load_seen():
    data = load_json(SEEN_FILE, {})
    # 迁移旧格式(纯 dict)到新格式
    if not isinstance(data, dict) or 'hashes' not in data:
        data = {'hashes': {}}
    # 清理超过7天的 hash 记录
    cutoff = (datetime.now() - timedelta(days=7)).isoformat()
    hashes = data.get('hashes', {})
    cleaned = {k: v for k, v in hashes.items() if v > cutoff}
    removed = len(hashes) - len(cleaned)
    if removed > 0:
        log(f"清理 {removed} 条过期 seen 记录")
    data['hashes'] = cleaned
    return data

def save_seen(seen):
    save_json(SEEN_FILE, seen)


GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN', '')
GITHUB_USER = os.environ.get('GITHUB_USER', 'liuhangbj')
GITHUB_REPO = 'news-briefing'
GITHUB_BRANCH = 'main'

def save_cubox_url(url, title, folder='Inbox', tags=None):
    """推送 URL 到 Cubox 指定文件夹"""
    if not CUBOX_API_URL:
        log("Cubox API URL 未配置,跳过推送")
        return False
    try:
        data = {
            'type': 'url',
            'content': url,
            'title': title,
            'folder': folder,
        }
        if tags:
            data['tags'] = tags if isinstance(tags, list) else [tags]
        req = urllib.request.Request(
            CUBOX_API_URL,
            data=json.dumps(data, ensure_ascii=False).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE
        with urllib.request.urlopen(req, context=ssl_ctx, timeout=15) as resp:
            result = json.loads(resp.read().decode('utf-8'))
        if isinstance(result, dict) and (result.get('code') == 200 or result.get('status') == '200'):
            log(f"Cubox URL推送成功: {title} -> 文件夹[{folder}]")
            return True
        else:
            log(f"Cubox推送返回: {result}")
            return False
    except Exception as e:
        log(f"Cubox推送失败: {e}")
        return False

# ========== 标题过滤规则 ==========

def score_article(title, source_name, desc=''):
    """词组匹配打分:命中词组加分,排除词直接丢弃"""
    text = (title or '') + ' ' + (desc or '')

    # 1. 全局过滤检查
    for filter_word in GLOBAL_FILTER:
        if filter_word in text:
            return -999, '过滤', ['全局过滤:' + filter_word], []

    score = 0
    matched_category = None
    matched_groups = []
    matched_details = []  # 命中的词组详情: [{'group': '词组名', 'keywords': [命中关键词列表]}]

    for group in KEYWORD_GROUPS:
        # 检查排除词
        excluded = False
        for ex in group.get('exclude', []):
            if ex in text:
                excluded = True
                break
        if excluded:
            continue

        # 检查触发词(命中任意一个),记录具体命中的关键词
        hit_keywords = []
        for kw in group.get('keywords', []):
            if kw in text:
                hit_keywords.append(kw)

        if not hit_keywords:
            continue

        # 检查必须词(如果配置了必须词,必须命中至少一个)
        required_list = group.get('required', [])
        if required_list:
            required_hit = False
            for req in required_list:
                if req in text:
                    required_hit = True
                    break
            if not required_hit:
                continue

        # 命中词组,加分
        bonus = group.get('bonus', 1)
        score += bonus
        matched_groups.append(group['name'])
        matched_details.append({
            'group': group['name'],
            'keywords': hit_keywords
        })
        if matched_category is None:
            matched_category = group['category']

    return score, matched_category, matched_groups, matched_details



# ========== 简报生成 ==========

def dedup_by_topic(articles):
    """按话题相似度去重,保留第一条"""
    unique = []
    skipped = 0
    for a in articles:
        title = a.get('title', '')
        is_dup = False
        for u in unique:
            if is_similar_topic(title, u.get('title', '')):
                is_dup = True
                break
        if is_dup:
            skipped += 1
        else:
            unique.append(a)
    if skipped > 0:
        log(f"话题级去重: 跳过 {skipped} 条相似文章")
    return unique

def generate_briefing():
    """生成候选列表简报"""
    now = datetime.now()
    log(f"生成简报: {now.strftime('%H:%M:%S')}")

    # === v4.2: 从 FreshRSS 缓存读取 ===
    # 读取 inoreader_briefing.json 缓存（快讯），不再直接抓取 RSS
    cache_file = os.path.join(os.path.dirname(PROJECT_DIR), 'rss-curation', 'cache', 'freshrss_briefing.json')
    all_items = []
    try:
        with open(cache_file, 'r', encoding='utf-8') as f:
            cached = json.load(f)
        log(f"[缓存] 读取 {len(cached)} 篇文章")
    except Exception as e:
        log(f"[缓存] 读取失败: {e}")
        cached = []

    seen = load_seen()
    source_stats = {}
    failed_sources = []

    # === v4.2: 时间窗口 - 昨天6:00到今天6:00 ===
    today_6am = now.replace(hour=6, minute=0, second=0, microsecond=0)
    yesterday_6am = today_6am - timedelta(days=1)

    log(f"[时间窗口] {yesterday_6am.strftime('%Y-%m-%d %H:%M')} ~ {today_6am.strftime('%Y-%m-%d %H:%M')}")

    for item in cached:
        h = article_hash(item['title'], item['url'])
        # briefing模式不跳过seen（全部处理），fetch模式才跳过

        item_pub = parse_pub_date(item.get('pub_date', ''))
        if item_pub:
            # 将UTC时间转换为本地时间后再比较，避免时区偏差
            item_pub = item_pub.astimezone().replace(tzinfo=None)
            # 只保留昨天6:00到今天6:00的文章
            if item_pub < yesterday_6am or item_pub >= today_6am:
                continue
        else:
            # 无发布时间，跳过（无法判断是否在时间窗口内）
            continue

        all_items.append(item)
        # 标记为已处理（供下次fetch去重）
        seen.setdefault('hashes', {})[h] = now.isoformat()

    # 保存去重记录
    save_seen(seen)

    log(f"[24h过滤] 剩余 {len(all_items)} 篇文章")

    if not all_items:
        log("缓存为空或全部已处理")
        return None, source_stats, failed_sources, 0, 0

    raw_count = len(all_items)  # 24h过滤后未去重数量

    # 按来源统计
    for item in all_items:
        src = item.get('source', '未知')
        source_stats[src] = source_stats.get(src, 0) + 1

    # 扁平化，准备处理

    # 清理 desc
    for item in all_items:
        item['desc'] = clean_desc(item.get('desc', ''))
        # 去掉源前缀如 [1.快讯] 等
        item['title'] = re.sub(r'^\[.*?\]\s*', '', item.get('title', ''))

    # URL 去重
    unique = []
    seen_urls = set()
    for item in all_items:
        url = item.get('url', '')
        if url and url in seen_urls:
            continue
        if url:
            seen_urls.add(url)
        unique.append(item)
    all_items = unique
    log(f"[URL去重] 剩余 {len(all_items)} 篇")

    # 话题级去重(跨源相似标题)
    all_items = dedup_by_topic(all_items)
    log(f"[话题去重] 剩余 {len(all_items)} 篇")

    # v4.2: 动态分类 + 打分排序
    all_articles = []
    for item in all_items:
        src = item.get('source', '')
        score, _, groups, details = score_article(item['title'], src, item.get('desc', ''))
        all_articles.append({
            'title': item['title'],
            'url': item['url'],
            'desc': item['desc'],
            'source': src,
            'score': score,
            'groups': groups,
            'details': details,
            'llm_score': 0,
            'llm_reason': '',
        })

    # 按关键词分降序排序（高分在前）
    all_articles.sort(key=lambda x: x['score'], reverse=True)



    # === v4.2: 候选列表模式 - 不自动筛选/分类/组织话题 ===
    # 脚本只负责阶段0：读取缓存、关键词打分、LLM参考打分、输出候选列表
    # 阶段1（人工筛选）由AI完成：逐条判断保留/剔除、手动组织热门话题、手动分类

    total = len(all_articles)
    log(f"[候选列表] 共 {total} 篇文章，按关键词分排序")

    # 生成候选列表HTML（不是成品简报）
    lines = []
    date_str = now.strftime('%m月%d日')
    time_str = now.strftime('%H:%M')

    # Markdown 格式候选列表，供 AI 直接读取
    lines.append(f'# 📋 候选列表 | {date_str} {time_str}')
    lines.append('')
    lines.append(f'> 共 {total} 篇文章 | 按关键词分排序 | 需逐条筛选保留/剔除')
    if failed_sources:
        lines.append(f'> ⚠️ 失败源: {", ".join(failed_sources)}')
    lines.append('')


    for i, a in enumerate(all_articles, 1):
        title = a['title']
        url = a['url']
        desc = a.get('desc', '')
        source = a.get('source', '')
        k_score = a.get('score', 0)
        groups = a.get('groups', [])
        details = a.get('details', [])
        is_high = k_score >= 1

        marker = '🔴' if is_high else '⚪'
        lines.append(f'### {marker} #{i:03d} [{title}]({url})' if url else f'### {marker} #{i:03d} {title}')
        lines.append(f'- **来源**: {source} | **关键词分**: {k_score}')
        # 命中的词组和关键词
        if details:
            hit_parts = []
            for d in details:
                gname = d.get('group', '')
                kws = d.get('keywords', [])
                if kws:
                    kw_str = '、'.join(kws[:3])  # 最多显示3个关键词
                    hit_parts.append(f'{gname}({kw_str})')
                else:
                    hit_parts.append(gname)
            lines.append(f'- **命中**: {", ".join(hit_parts)}')
        if desc:
            lines.append(f'- **摘要**: {desc}')
        lines.append('')

    lines.append('---')
    lines.append(f'*{time_str} 生成 | 候选列表供 AI 筛选*')

    candidates_md = '\n'.join(lines)
    return candidates_md, source_stats, failed_sources, raw_count, total

def save_candidates(text):
    """保存候选列表 Markdown（供 AI 读取筛选）"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = f"{OUTPUT_DIR}/candidates_{datetime.now().strftime('%Y%m%d')}.md"
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)

    # 记录候选列表路径
    last_candidates = f"{DATA_DIR}/last_candidates_path.txt"
    with open(last_candidates, 'w', encoding='utf-8') as f:
        f.write(path)

    log(f"候选列表已保存: {path}")
    return path

def save_final_briefing(text):
    """保存最终简报Markdown到Obsidian并自动推送到GitHub（AI人工筛选后调用）"""
    # 保存原始 Markdown 到 Obsidian 仓库
    obsidian_dir = "/Users/hangbits/Library/Mobile Documents/iCloud~md~obsidian/Documents/HangBits/Article/0 - 每日新闻简报"
    os.makedirs(obsidian_dir, exist_ok=True)
    date_iso = datetime.now().strftime('%Y-%m-%d')
    date_str = datetime.now().strftime('%Y%m%d')
    md_path = f"{obsidian_dir}/{date_iso}.md"
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(text)
    log(f"Markdown 已保存到 Obsidian: {md_path}")

    # 转换为 HTML 保存到输出目录
    html_text = text
    if not text.strip().startswith('<!DOCTYPE html') and not text.strip().startswith('<html'):
        try:
            from md2html import markdown_to_html
            html_text = markdown_to_html(text)
        except Exception as e:
            log(f"Markdown转HTML失败: {e}，保存原始文本")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    html_path = f"{OUTPUT_DIR}/news_briefing_{date_str}.html"
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html_text)

    # 记录最后简报路径
    last_briefing = f"{DATA_DIR}/last_briefing_path.txt"
    with open(last_briefing, 'w', encoding='utf-8') as f:
        f.write(html_path)

    log(f"HTML 已保存: {html_path}")

    # === 自动推送到GitHub ===
    github_url = push_to_github(html_path, date_str)
    if github_url:
        update_index_page(os.environ.get('GITHUB_TOKEN', ''))
        log(f"✅ 推送完成: GitHub")
    else:
        log(f"⚠️ GitHub推送失败")

    return md_path


def push_to_github(file_path, date_str):
    """推送简报到GitHub仓库"""
    import base64
    import urllib.request

    # 从环境变量或.env读取token
    token = os.environ.get('GITHUB_TOKEN', '')
    if not token:
        try:
            env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
            with open(env_path) as f:
                for line in f:
                    if line.startswith('GITHUB_TOKEN='):
                        token = line.strip().split('=', 1)[1].strip()
                        break
        except Exception:
            pass

    if not token:
        log("GitHub token未配置,跳过推送")
        return None

    user = GITHUB_USER
    repo = GITHUB_REPO
    filename = f'news_briefing_{date_str}.html'

    try:
        with open(file_path, 'rb') as f:
            content = base64.b64encode(f.read()).decode()

        # 检查文件是否存在（获取sha）
        req = urllib.request.Request(
            f'https://api.github.com/repos/{user}/{repo}/contents/{filename}',
            headers={'Authorization': f'token {token}', 'User-Agent': 'news-briefing'}
        )
        sha = None
        try:
            resp = urllib.request.urlopen(req, timeout=10)
            data = json.loads(resp.read())
            sha = data.get('sha')
        except urllib.error.HTTPError as e:
            if e.code != 404:
                log(f"GitHub检查文件失败: {e.code}")

        # 创建或更新文件
        payload = {
            'message': f'news briefing {date_str}',
            'content': content,
        }
        if sha:
            payload['sha'] = sha

        req = urllib.request.Request(
            f'https://api.github.com/repos/{user}/{repo}/contents/{filename}',
            data=json.dumps(payload).encode(),
            headers={
                'Authorization': f'token {token}',
                'Content-Type': 'application/json',
                'User-Agent': 'news-briefing'
            },
            method='PUT'
        )
        resp = urllib.request.urlopen(req, timeout=30)
        data = json.loads(resp.read())

        github_url = f'https://{user}.github.io/{repo}/{filename}'
        log(f"GitHub推送成功: {github_url}")
        return github_url

    except Exception as e:
        log(f"GitHub推送失败: {e}")
        return None


def update_index_page(token, user='liuhangbj', repo='news-briefing'):
    """更新GitHub仓库的index.html，列出所有简报文件"""
    import urllib.request, ssl, base64

    # 如果 token 为空，尝试从 .env 读取
    if not token:
        try:
            env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
            with open(env_path) as f:
                for line in f:
                    if line.startswith('GITHUB_TOKEN='):
                        token = line.strip().split('=', 1)[1].strip()
                        break
        except Exception:
            pass

    if not token:
        log("GitHub token未配置,跳过index更新")
        return False

    try:
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE

        # 获取仓库文件列表
        req = urllib.request.Request(
            f'https://api.github.com/repos/{user}/{repo}/contents/',
            headers={'Authorization': f'token {token}', 'User-Agent': 'news-briefing'}
        )
        resp = urllib.request.urlopen(req, context=ssl_ctx, timeout=15)
        files = json.loads(resp.read().decode())

        # 提取所有 news_briefing_YYYYMMDD.html 文件
        briefings = []
        for f in files:
            name = f.get('name', '')
            if name.startswith('news_briefing_') and name.endswith('.html'):
                date_part = name.replace('news_briefing_', '').replace('.html', '')
                briefings.append((date_part, name))

        # 按日期倒序
        briefings.sort(reverse=True)

        # 生成 HTML
        items = []
        for i, (date_str, filename) in enumerate(briefings):
            month = int(date_str[4:6])
            day = int(date_str[6:8])
            label = f"{month}月{day}日 简报"
            latest = ' <span class="date">最新</span>' if i == 0 else ''
            items.append(f'  <li><a href="{filename}">{label}</a>{latest}</li>')

        html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <title>每日新闻简报归档</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; max-width: 600px; margin: 40px auto; padding: 20px; color: #333; }}
    h1 {{ font-size: 24px; border-bottom: 2px solid #333; padding-bottom: 10px; }}
    ul {{ list-style: none; padding: 0; }}
    li {{ margin: 10px 0; padding: 10px; background: #f5f5f5; border-radius: 4px; }}
    a {{ color: #1565c0; text-decoration: none; font-size: 16px; }}
    a:hover {{ text-decoration: underline; }}
    .date {{ color: #888; font-size: 13px; }}
  </style>
</head>
<body>
<h1>📰 每日新闻简报归档</h1>
<ul>
''' + '\n'.join(items) + '''
</ul>
</body>
</html>'''

        # 获取 index.html 的 sha
        sha = None
        try:
            req = urllib.request.Request(
                f'https://api.github.com/repos/{user}/{repo}/contents/index.html',
                headers={'Authorization': f'token {token}', 'User-Agent': 'news-briefing'}
            )
            resp = urllib.request.urlopen(req, context=ssl_ctx, timeout=10)
            data = json.loads(resp.read().decode())
            sha = data.get('sha')
        except urllib.error.HTTPError as e:
            if e.code != 404:
                log(f"获取index.html失败: {e.code}")

        # 上传更新
        payload = {
            'message': 'update index',
            'content': base64.b64encode(html.encode('utf-8')).decode(),
        }
        if sha:
            payload['sha'] = sha

        req = urllib.request.Request(
            f'https://api.github.com/repos/{user}/{repo}/contents/index.html',
            data=json.dumps(payload).encode(),
            headers={
                'Authorization': f'token {token}',
                'Content-Type': 'application/json',
                'User-Agent': 'news-briefing'
            },
            method='PUT'
        )
        urllib.request.urlopen(req, context=ssl_ctx, timeout=30)
        log("index.html 已更新")
        return True

    except Exception as e:
        log(f"更新index.html失败: {e}")
        return False


def save_selected_list(selected_ids, all_articles, date_str=None):
    """保存人工筛选后的精选列表（供第二步提取完整内容）"""
    if date_str is None:
        date_str = datetime.now().strftime('%Y%m%d')
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    selected_path = f"{OUTPUT_DIR}/selected_{date_str}.json"
    
    selected_items = []
    for idx in selected_ids:
        if 1 <= idx <= len(all_articles):
            a = all_articles[idx - 1]  # 编号从1开始
            selected_items.append({
                'num': idx,
                'title': a.get('title', ''),
                'url': a.get('url', ''),
                'source': a.get('source', ''),
                'score': a.get('score', 0),
                'marker': '🔴' if a.get('score', 0) >= 1 else '⚪'
            })
    
    with open(selected_path, 'w', encoding='utf-8') as f:
        json.dump(selected_items, f, ensure_ascii=False, indent=2)
    
    log(f"精选列表已保存: {selected_path} ({len(selected_items)} 篇)")
    return selected_path


def extract_full_content(selected_file=None, cache_file=None, output_file=None, date_str=None):
    """第二步：从缓存库提取入选文章的完整内容，生成筛选全文数据列表
    
    两步筛选流程：
    1. 先生成 candidates_YYYYMMDD.md，人工逐条读标题筛选
    2. 保存 selected_YYYYMMDD.json（编号列表）
    3. 调用此函数，从 freshrss_briefing.json 缓存提取完整内容
    """
    if date_str is None:
        date_str = datetime.now().strftime('%Y%m%d')
    
    if selected_file is None:
        selected_file = f"{OUTPUT_DIR}/selected_{date_str}.json"
    if cache_file is None:
        cache_file = os.path.join(os.path.dirname(PROJECT_DIR), 'rss-curation', 'cache', 'freshrss_briefing.json')
    if output_file is None:
        output_file = f"{OUTPUT_DIR}/filtered_full_{date_str}.md"
    
    # 读取精选列表
    try:
        with open(selected_file, 'r', encoding='utf-8') as f:
            selected_list = json.load(f)
        log(f"[精选列表] 读取 {len(selected_list)} 篇")
    except Exception as e:
        log(f"[精选列表] 读取失败: {e}")
        return None
    
    # 读取缓存
    try:
        with open(cache_file, 'r', encoding='utf-8') as f:
            cache = json.load(f)
        log(f"[缓存] 读取 {len(cache)} 篇文章")
    except Exception as e:
        log(f"[缓存] 读取失败: {e}")
        return None
    
    # 建立 URL -> 缓存项映射
    cache_by_url = {}
    for item in cache:
        url = item.get('url', '')
        if url:
            cache_by_url[url] = item
    
    # 提取完整内容
    lines = []
    lines.append(f'# {date_str[:4]}-{date_str[4:6]}-{date_str[6:]} 筛选全文数据列表')
    lines.append(f'> 从缓存库提取完整内容 | 共 {len(selected_list)} 篇')
    lines.append('')
    
    matched = 0
    missing = 0
    lengths = []
    
    for item in selected_list:
        url = item.get('url', '')
        cache_item = cache_by_url.get(url)
        
        if not cache_item:
            missing += 1
            log(f"[缺失] #{item.get('num', '?')} {item.get('title', '')[:40]}")
            continue
        
        matched += 1
        desc = cache_item.get('desc', '')
        source = cache_item.get('source', '')
        pub_date = cache_item.get('pub_date', '')
        lengths.append(len(desc))
        
        lines.append(f"### {item.get('marker', '⚪')} #{item.get('num', 0):03d} [score={item.get('score', 0)}]")
        lines.append(f"**标题**: {item.get('title', '')}")
        lines.append(f"**链接**: {url}")
        lines.append(f"**来源**: {source}")
        lines.append(f"**发布时间**: {pub_date}")
        lines.append(f"**字数**: {len(desc)}")
        lines.append('**正文**:')
        lines.append(desc)
        lines.append('')
        lines.append('---')
        lines.append('')
    
    # 写入文件
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    
    # 统计
    if lengths:
        log(f"[提取完成] 匹配 {matched} 篇, 缺失 {missing} 篇")
        log(f"[字数统计] 最小 {min(lengths)}, 最大 {max(lengths)}, 中位数 {sorted(lengths)[len(lengths)//2]}, 平均 {sum(lengths)//len(lengths)}")
        
        bins = [(0, 100), (100, 300), (300, 500), (500, 1000), (1000, 1500), (1500, 2000), (2000, 9999), (10000, 99999)]
        for lo, hi in bins:
            count = sum(1 for l in lengths if lo <= l < hi)
            if count > 0:
                pct = count / len(lengths) * 100
                log(f"  {lo:5d}-{hi:5d} 字: {count:3d} ({pct:5.1f}%)")
    
    log(f"筛选全文列表已保存: {output_file} ({os.path.getsize(output_file):,} 字节)")
    return output_file


def main():
    import sys
    
    # 解析命令行参数
    mode = 'generate'
    date_str = None
    selected_file = None
    
    for arg in sys.argv[1:]:
        if arg.startswith('--mode='):
            mode = arg.split('=', 1)[1]
        elif arg.startswith('--date='):
            date_str = arg.split('=', 1)[1]
        elif arg.startswith('--selected='):
            selected_file = arg.split('=', 1)[1]
    
    log("=" * 50)
    
    if mode == 'generate':
        log("News Briefing v4.2 - 候选列表生成（第一步）")
        log("=" * 50)
        
        candidates_md, stats, failed, raw_count, total = generate_briefing()
        if candidates_md:
            path = save_candidates(candidates_md)
            log(f"完成: 24h过滤后{raw_count}条, 话题去重后{total}条, {len(stats)}个源成功, {len(failed)}个失败")
            log(f"候选列表路径: {path}")
            log(f"下一步: 人工逐条读标题筛选，保存 selected_YYYYMMDD.json")
        else:
            log("候选列表生成失败")
    
    elif mode == 'extract':
        log("News Briefing v4.2 - 提取完整内容（第二步）")
        log("=" * 50)
        
        result = extract_full_content(selected_file=selected_file, date_str=date_str)
        if result:
            log(f"筛选全文列表已生成: {result}")
        else:
            log("提取失败")
    
    else:
        log(f"未知模式: {mode}")
        log("用法: python news_briefing.py [--mode=generate|extract] [--date=YYYYMMDD] [--selected=path.json]")
    
    log("=" * 50)

if __name__ == '__main__':
    main()
