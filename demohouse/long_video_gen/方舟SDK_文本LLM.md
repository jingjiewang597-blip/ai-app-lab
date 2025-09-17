# 大语言模型调用
import os
# 通过 ppip install 'volcengine-python-sdk[ark]' --upgrade 安装方舟SDK
from volcenginesdkarkruntime import Ark

# 从环境变量中获取您的API KEY，配置方法见：https://www.volcengine.com/docs/82379/1399008
api_key = os.getenv('ARK_API_KEY')
# 替换 <MODEL> 为模型的Model ID
model = "<MODEL>"

# 初始化Ark客户端
client = Ark(
    api_key = api_key,
)

# 创建一个对话请求
completion = client.chat.completions.create(
    model = model,
    messages = [
        {"role": "user", "content": "请将下面内容进行结构化处理：火山方舟是火山引擎推出的大模型服务平台，提供模型训练、推理、评测、精调等全方位功能与服务，并重点支撑大模型生态。 火山方舟通过稳定可靠的安全互信方案，保障模型提供方的模型安全与模型使用者的信息安全，加速大模型能力渗透到千行百业，助力模型提供方和使用者实现商业新增长。"},
    ],
)

print(completion.choices[0].message.content)