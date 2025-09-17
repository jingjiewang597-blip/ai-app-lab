import os
import time  
# 通过 pip install 'volcengine-python-sdk[ark]' 安装方舟SDK
from volcenginesdkarkruntime import Ark

# 请确保您已将 API Key 存储在环境变量 ARK_API_KEY 中
# 初始化Ark客户端，从环境变量中读取您的API Key
client = Ark(
    # 此为默认路径，您可根据业务所在地域进行配置
    base_url="https://ark.cn-beijing.volces.com/api/v3",
    # 从环境变量中获取您的 API Key。此为默认方式，您可根据需要进行修改
    api_key=os.environ.get("ARK_API_KEY"),
)

if __name__ == "__main__":
    print("----- create request -----")
    create_result = client.content_generation.tasks.create(
        model="……", # 模型 Model ID
        content=[
            {
                # 文本提示词与参数组合
                "type": "text",
                "text": "天空的云飘动着，路上的车辆行驶  --resolution 720p  --duration 5 --camerafixed false --watermark true"
            },
            {
                # 首帧图片URL
                "type": "image_url",
                "image_url": {
                    "url": "https://ark-project.tos-cn-beijing.volces.com/doc_image/see_i2v.jpeg" 
                }
            }
        ]
    )
    print(create_result)

    # 轮询查询部分
    print("----- polling task status -----")
    task_id = create_result.id
    while True:
        get_result = client.content_generation.tasks.get(task_id=task_id)
        status = get_result.status
        if status == "succeeded":
            print("----- task succeeded -----")
            # 返回生成视频的URL
            print(get_result.content.video_url)
            break
        elif status == "failed":
            print("----- task failed -----")
            print(f"Error: {get_result.error}")
            break
        else:
            print(f"Current status: {status}, Retrying after 1 seconds...")
            time.sleep(1)

# 更多操作请参考下述网址
# 查询视频生成任务列表：https://www.volcengine.com/docs/82379/1521675
# 取消或删除视频生成任务：https://www.volcengine.com/docs/82379/1521720

注意：
图片如果是本地图片，content.image_url.url可以是图片的Base64编码

Base64编码：请遵循此格式data:image/<图片格式>;base64,<Base64编码>，
注意 <图片格式> 需小写，如 data:image/png;base64,{base64_image}。
图片格式清单：
图片格式：JPEG，图片格式为：image/jpeg
图片格式：PNG，图片格式为：image/png
图片格式：GIF，图片格式为：image/gif
图片格式：WEBP，图片格式为：image/webp
