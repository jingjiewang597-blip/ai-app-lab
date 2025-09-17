# 图片生成
import os
# 通过 pip install 'volcengine-python-sdk[ark]' --upgrade 安装方舟SDK
from volcenginesdkarkruntime import Ark

# 请确保您已将 API Key 存储在环境变量 ARK_API_KEY 中
# 初始化Ark客户端，从环境变量中读取您的API Key
client = Ark(
    # 此为默认路径，您可根据业务所在地域进行配置
    base_url="https://ark.cn-beijing.volces.com/api/v3",
    # 从环境变量中获取您的 API Key。此为默认方式，您可根据需要进行修改
    api_key=os.environ.get("ARK_API_KEY"),
)

imagesResponse = client.images.generate(
    model="doubao-seedream-3-0-t2i-250415",
    prompt="鱼眼镜头，一只猫咪的头部，画面呈现出猫咪的五官因为拍摄方式扭曲的效果。"
)

print(imagesResponse.data[0].url)

