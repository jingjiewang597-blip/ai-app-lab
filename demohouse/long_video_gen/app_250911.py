import streamlit as st
import os
import json
import requests
from pathlib import Path
from PIL import Image
import io
import base64
from volcenginesdkarkruntime import Ark
from configparser import ConfigParser
from moviepy import VideoFileClip, concatenate_videoclips, AudioFileClip
import time
import asyncio
import websockets
import uuid
import json
import sys
import os

# 添加protocols模块路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '方舟API_语音合成'))
from protocols import MsgType, receive_message, full_client_request

# 配置页面
st.set_page_config(
    page_title="长视频生成应用",
    page_icon="🎬",
    layout="wide"
)

# 读取配置文件
config = ConfigParser()
config.read('方舟模型配置.cfg')

# 初始化方舟客户端
api_key = config.get('DEFAULT', 'api_key')
base_url = config.get('DEFAULT', 'base_url')
seedream_model_id = config.get('DEFAULT', 'seedream_model_id')
seedance_model_id = config.get('DEFAULT', 'seedance_model_id')
doubao_seed_model_id = config.get('DEFAULT', 'doubao_seed_model_id')

# 语音合成配置
tts_appid = config.get('DEFAULT', 'appid')
tts_access_token = config.get('DEFAULT', 'access_token')
tts_secret_key = config.get('DEFAULT', 'secret_key')
tts_voice_type = config.get('DEFAULT', 'voice_type')

client = Ark(base_url=base_url, api_key=api_key)

# 文件路径配置
FILE_DIR = Path("文件生成")
SCENE_INPUT_FILE = FILE_DIR / "用户输入场景.md"
STORYBOARD_FILE = FILE_DIR / "分镜生成结果.md"
EXTRACTION_FILE = FILE_DIR / "分镜信息提取结果.json"
VIDEO_DIR = FILE_DIR / "分镜视频"
AUDIO_DIR = FILE_DIR / "分镜音频"
AV_DIR = FILE_DIR / "音视频"

# 确保目录存在
FILE_DIR.mkdir(exist_ok=True)
VIDEO_DIR.mkdir(exist_ok=True)
AUDIO_DIR.mkdir(exist_ok=True)
AV_DIR.mkdir(exist_ok=True)

# 读取Prompt文件
def read_prompt_file(filename):
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        return ""

STORYBOARD_PROMPT = read_prompt_file("分镜生成Prompt.md")
EXTRACTION_PROMPT = read_prompt_file("分镜信息提取Prompt.md")
IMAGE_PROMPT_TEMPLATE = read_prompt_file("分镜图片生成Prompt.md")
VIDEO_PROMPT_PROMPT = read_prompt_file("分镜生成视频Prompt的Prompt.md")

# 工具函数
def save_file(content, filepath):
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

def read_file(filepath):
    if filepath.exists():
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    return ""

def call_doubao_seed_model(messages):
    try:
        completion = client.chat.completions.create(
            model=doubao_seed_model_id,
            messages=messages,
        )
        return completion.choices[0].message.content
    except Exception as e:
        st.error(f"调用豆包Seed1.6模型失败: {e}")
        return ""

def generate_storyboard(user_input):
    prompt = STORYBOARD_PROMPT.replace("{USER_INPUT}", user_input)
    messages = [{"role": "user", "content": prompt}]
    result = call_doubao_seed_model(messages)
    if result:
        save_file(result, STORYBOARD_FILE)
    return result

def extract_storyboard_info(storyboard_content):
    prompt = EXTRACTION_PROMPT.replace("{{input}}", storyboard_content)
    messages = [{"role": "user", "content": prompt}]
    result = call_doubao_seed_model(messages)
    if result:
        try:
            json_data = json.loads(result)
            save_file(json.dumps(json_data, ensure_ascii=False, indent=2), EXTRACTION_FILE)
            return json_data
        except json.JSONDecodeError:
            st.error("分镜信息提取结果不是有效的JSON格式")
            return None
    return None

def generate_scene_image(scene_description, index):
    prompt = IMAGE_PROMPT_TEMPLATE.replace("{场景}", scene_description)
    try:
        response = client.images.generate(
            model=seedream_model_id,
            prompt=prompt,
            size="1024x1024"
        )
        image_url = response.data[0].url
        img_response = requests.get(image_url)
        img = Image.open(io.BytesIO(img_response.content))
        image_path = FILE_DIR / f"分镜图片_{index+1}.jpg"
        img.save(image_path)
        return img, image_path
    except Exception as e:
        st.error(f"生成图片失败: {e}")
        return None, None

def generate_video_prompt(scene_description, index):
    messages = [
        {"role": "system", "content": VIDEO_PROMPT_PROMPT},
        {"role": "user", "content": scene_description}
    ]
    result = call_doubao_seed_model(messages)
    if result:
        prompt_path = FILE_DIR / f"生成视频Prompt_{index+1}.md"
        save_file(result, prompt_path)
    return result

def generate_scene_video(video_prompt, image_path, index):
    try:
        with open(image_path, 'rb') as f:
            image_data = base64.b64encode(f.read()).decode('utf-8')
        
        # 使用content_generation.tasks.create进行视频生成
        create_result = client.content_generation.tasks.create(
            model=seedance_model_id,
            content=[
                {
                    "type": "text",
                    "text": video_prompt  # 只使用视频提示词，不添加参数
                },
                {
                    "type": "image_url", 
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{image_data}"
                    }
                }
            ]
        )
        
        task_id = create_result.id
        
        # 轮询任务状态
        while True:
            get_result = client.content_generation.tasks.get(task_id=task_id)
            status = get_result.status
            if status == "succeeded":
                video_url = get_result.content.video_url
                break
            elif status == "failed":
                st.error(f"视频生成任务失败: {get_result.error}")
                return None, None
            else:
                time.sleep(1)
        
        url_path = FILE_DIR / f"分镜视频_{index+1}.txt"
        save_file(video_url, url_path)
        video_response = requests.get(video_url)
        video_path = VIDEO_DIR / f"分镜视频_{index+1}.mp4"
        with open(video_path, 'wb') as f:
            f.write(video_response.content)
        return video_path, video_url
    except Exception as e:
        st.error(f"生成视频失败: {e}")
        return None, None

# 语音合成函数
async def generate_scene_audio(narration, index):
    """生成场景音频"""
    try:
        # WebSocket连接配置
        endpoint = "wss://openspeech.bytedance.com/api/v1/tts/ws_binary"
        headers = {
            "Authorization": f"Bearer;{tts_access_token}",
        }
        
        # 连接WebSocket
        websocket = await websockets.connect(
            endpoint, additional_headers=headers, max_size=10 * 1024 * 1024
        )
        
        try:
            # 准备请求负载
            request = {
                "app": {
                    "appid": tts_appid,
                    "token": tts_access_token,
                    "cluster": "volcano_tts",
                },
                "user": {
                    "uid": str(uuid.uuid4()),
                },
                "audio": {
                    "voice_type": tts_voice_type,
                    "encoding": "wav",
                },
                "request": {
                    "reqid": str(uuid.uuid4()),
                    "text": narration,
                    "operation": "submit",
                    "with_timestamp": "1",
                    "extra_param": json.dumps({
                        "disable_markdown_filter": False,
                    }),
                },
            }
            
            # 使用协议库发送请求
            await full_client_request(websocket, json.dumps(request).encode())
            
            # 接收音频数据
            audio_data = bytearray()
            while True:
                msg = await receive_message(websocket)
                
                if msg.type == MsgType.FrontEndResultServer:
                    continue
                elif msg.type == MsgType.AudioOnlyServer:
                    audio_data.extend(msg.payload)
                    if msg.sequence < 0:  # Last message
                        break
                else:
                    st.error(f"语音合成失败: {msg}")
                    return None
            
            # 保存音频文件（如果有数据）
            if audio_data:
                audio_path = AUDIO_DIR / f"分镜音频_{index+1}.wav"
                with open(audio_path, 'wb') as f:
                    f.write(audio_data)
                
                # 保存音频URL到文件
                url_path = FILE_DIR / f"分镜音频_{index+1}.txt"
                save_file(str(audio_path), url_path)
                
                return audio_path
            else:
                st.error("未接收到音频数据")
                return None
            
        finally:
            await websocket.close()
            
    except Exception as e:
        st.error(f"生成音频失败: {e}")
        return None

# 音视频合成函数
def concatenate_audio_video(video_path, audio_path, index):
    """将视频和音频合成为有音频的视频"""
    try:
        video_clip = VideoFileClip(str(video_path))
        audio_clip = AudioFileClip(str(audio_path))
        
        # 设置视频的音频（兼容moviepy 2.0.0）
        # 在moviepy 2.0.0中，set_audio方法可能不可用，使用audio参数
        final_clip = video_clip.with_audio(audio_clip)
        
        # 保存合成后的视频
        av_path = AV_DIR / f"音视频_{index+1}.mp4"
        final_clip.write_videofile(str(av_path), codec='libx264', audio_codec='aac')
        
        return av_path
        
    except Exception as e:
        st.error(f"音视频合成失败: {e}")
        return None

# 视频拼接函数
def concatenate_all_videos():
    """拼接所有音视频为一个长视频"""
    try:
        av_files = sorted(AV_DIR.glob("音视频_*.mp4"))
        if not av_files:
            st.error("没有找到音视频文件")
            return None
        
        clips = [VideoFileClip(str(av_file)) for av_file in av_files]
        final_clip = concatenate_videoclips(clips)
        
        final_path = FILE_DIR / "拼接视频.mp4"
        final_clip.write_videofile(str(final_path), codec='libx264', audio_codec='aac')
        
        return final_path
        
    except Exception as e:
        st.error(f"视频拼接失败: {e}")
        return None

# 主应用
def main():
    st.title("🎬 长视频生成应用")
    
    # 初始化session state
    if 'storyboard_data' not in st.session_state:
        st.session_state.storyboard_data = None
    if 'extracted_data' not in st.session_state:
        st.session_state.extracted_data = None
    if 'scene_images' not in st.session_state:
        st.session_state.scene_images = {}
    if 'video_prompts' not in st.session_state:
        st.session_state.video_prompts = {}
    if 'scene_videos' not in st.session_state:
        st.session_state.scene_videos = {}
    if 'scene_audios' not in st.session_state:
        st.session_state.scene_audios = {}
    if 'scene_avs' not in st.session_state:
        st.session_state.scene_avs = {}
    
    # 步骤一：分镜生成
    st.header("步骤一：分镜生成")
    existing_input = read_file(SCENE_INPUT_FILE)
    user_input = st.text_area("请输入场景需求：", value=existing_input, height=100)
    
    if st.button("分镜生成", key="generate_storyboard"):
        if user_input:
            save_file(user_input, SCENE_INPUT_FILE)
            with st.spinner("正在生成分镜信息..."):
                storyboard = generate_storyboard(user_input)
                if storyboard:
                    st.session_state.storyboard_data = storyboard
                    st.success("分镜生成成功！")
                else:
                    st.error("分镜生成失败")
        else:
            st.warning("请输入场景需求")
    
    # 清空按钮
    if st.button("清空所有数据", key="clear_all_data"):
        st.session_state.storyboard_data = None
        st.session_state.extracted_data = None
        st.session_state.scene_images = {}
        st.session_state.video_prompts = {}
        st.session_state.scene_videos = {}
        st.session_state.scene_audios = {}
        st.session_state.scene_avs = {}
        
        # 删除所有生成的文件
        import shutil
        if FILE_DIR.exists():
            shutil.rmtree(FILE_DIR)
        FILE_DIR.mkdir(exist_ok=True)
        VIDEO_DIR.mkdir(exist_ok=True)
        AUDIO_DIR.mkdir(exist_ok=True)
        AV_DIR.mkdir(exist_ok=True)
        
        st.success("所有数据已清空！可以开始新的任务了。")
        st.rerun()
    
    # 显示分镜生成结果
    existing_storyboard = read_file(STORYBOARD_FILE)
    if existing_storyboard:
        st.session_state.storyboard_data = existing_storyboard
    
    if st.session_state.storyboard_data:
        st.subheader("分镜生成结果")
        st.text_area("分镜内容", st.session_state.storyboard_data, height=300)
    
    # 步骤二：分镜信息提取
    if st.session_state.storyboard_data:
        st.header("步骤二：分镜信息提取")
        if st.button("提取分镜信息", key="extract_info"):
            with st.spinner("正在提取分镜信息..."):
                extracted_data = extract_storyboard_info(st.session_state.storyboard_data)
                if extracted_data:
                    st.session_state.extracted_data = extracted_data
                    st.success("分镜信息提取成功！")
                else:
                    st.error("分镜信息提取失败")
        
        existing_extraction = read_file(EXTRACTION_FILE)
        if existing_extraction:
            try:
                st.session_state.extracted_data = json.loads(existing_extraction)
            except json.JSONDecodeError:
                pass
        
        if st.session_state.extracted_data:
            st.subheader("提取结果")
            col1, col2 = st.columns(2)
            with col1:
                st.text_area("画风", st.session_state.extracted_data.get("画风", ""), height=100)
            with col2:
                st.text_area("角色设定", st.session_state.extracted_data.get("角色设定", ""), height=100)
            
            # 场景列表
            st.subheader("场景列表")
            scene_list = st.session_state.extracted_data.get("场景列表", [])
            for i, scene in enumerate(scene_list):
                st.markdown(f"**场景 {i+1}**")
                col1, col2 = st.columns(2)
                with col1:
                    st.text_area(f"场景描述 {i+1}", scene.get("场景", ""), height=100, key=f"scene_{i}")
                with col2:
                    st.text_area(f"旁白 {i+1}", scene.get("旁白", ""), height=100, key=f"narration_{i}")
                
                # 图片生成
                if st.button(f"生成分镜图片 {i+1}", key=f"generate_image_{i}"):
                    with st.spinner(f"正在生成场景 {i+1} 的图片..."):
                        img, img_path = generate_scene_image(scene.get("场景", ""), i)
                        if img:
                            st.session_state.scene_images[i] = img
                            st.success(f"场景 {i+1} 图片生成成功！")
                        else:
                            st.error(f"场景 {i+1} 图片生成失败")
                
                image_path = FILE_DIR / f"分镜图片_{i+1}.jpg"
                if image_path.exists():
                    st.image(str(image_path), caption=f"场景 {i+1} 图片")
                
                # 视频Prompt生成
                if st.button(f"生成视频Prompt {i+1}", key=f"generate_video_prompt_{i}"):
                    with st.spinner(f"正在生成场景 {i+1} 的视频Prompt..."):
                        video_prompt = generate_video_prompt(scene.get("场景", ""), i)
                        if video_prompt:
                            st.session_state.video_prompts[i] = video_prompt
                            st.success(f"场景 {i+1} 视频Prompt生成成功！")
                        else:
                            st.error(f"场景 {i+1} 视频Prompt生成失败")
                
                # 显示视频Prompt（优先显示session state中的，如果没有则显示文件中的）
                prompt_path = FILE_DIR / f"生成视频Prompt_{i+1}.md"
                if i in st.session_state.video_prompts:
                    st.text_area(f"视频Prompt {i+1}", st.session_state.video_prompts[i], height=100, key=f"video_prompt_{i}")
                elif prompt_path.exists():
                    video_prompt = read_file(prompt_path)
                    st.text_area(f"视频Prompt {i+1}", video_prompt, height=100, key=f"video_prompt_{i}")
                
                # 音频生成
                if st.button(f"生成音频 {i+1}", key=f"generate_audio_{i}"):
                    narration = scene.get("旁白", "")
                    if narration:
                        with st.spinner(f"正在生成场景 {i+1} 的音频..."):
                            audio_path = asyncio.run(generate_scene_audio(narration, i))
                            if audio_path:
                                st.session_state.scene_audios[i] = audio_path
                                st.success(f"场景 {i+1} 音频生成成功！")
                            else:
                                st.error(f"场景 {i+1} 音频生成失败")
                    else:
                        st.warning("该场景没有旁白内容")
                
                # 显示音频
                audio_path = AUDIO_DIR / f"分镜音频_{i+1}.wav"
                if audio_path.exists():
                    st.audio(str(audio_path))
                
                # 视频生成
                if st.button(f"生成分镜视频 {i+1}", key=f"generate_video_{i}"):
                    image_path = FILE_DIR / f"分镜图片_{i+1}.jpg"
                    prompt_path = FILE_DIR / f"生成视频Prompt_{i+1}.md"
                    audio_path = AUDIO_DIR / f"分镜音频_{i+1}.wav"
                    # 辅助函数：获取视频时长
                    def get_video_duration(video_path):
                        try:
                            clip = VideoFileClip(str(video_path))
                            duration = clip.duration
                            clip.close()
                            return duration
                        except Exception as e:
                            st.error(f"获取视频时长失败: {e}")
                            return None

                    # 辅助函数：获取音频时长
                    def get_audio_duration(audio_path):
                        try:
                            clip = AudioFileClip(str(audio_path))
                            duration = clip.duration
                            clip.close()
                            return duration
                        except Exception as e:
                            st.error(f"获取音频时长失败: {e}")
                            return None

                    # 辅助函数：截取视频到指定时长
                    def trim_video_to_duration(video_path, target_duration, output_path):
                        try:
                            # 使用ffmpeg直接截取视频，这是最可靠的方法
                            import subprocess
                            
                            # 首先获取视频的实际时长
                            clip = VideoFileClip(str(video_path))
                            actual_duration = clip.duration
                            clip.close()
                            
                            if actual_duration > target_duration:
                                # 使用ffmpeg截取视频
                                input_file = str(video_path)
                                output_file = str(output_path)
                                
                                # 使用ffmpeg的-t参数指定持续时间
                                result = subprocess.run([
                                    'ffmpeg', '-i', input_file, '-t', str(target_duration),
                                    '-c', 'copy', output_file, '-y'
                                ], capture_output=True, text=True)
                                
                                if result.returncode == 0:
                                    return output_path
                                else:
                                    st.error(f"ffmpeg截取视频失败: {result.stderr}")
                                    return None
                            else:
                                # 如果视频时长已经小于等于目标时长，直接复制文件
                                import shutil
                                shutil.copy2(video_path, output_path)
                            return output_path
                            
                        except Exception as e:
                            st.error(f"截取视频失败: {e}")
                        return None

                    # 辅助函数：截取视频尾帧
                    def extract_last_frame(video_path, output_image_path):
                        try:
                            clip = VideoFileClip(str(video_path))
                            # 获取视频的最后一帧（在结束前0.1秒的位置）
                            last_frame_time = max(0, clip.duration - 0.1)
                            last_frame = clip.get_frame(last_frame_time)
                            clip.close()
                            
                            # 保存尾帧为图片
                            from PIL import Image
                            img = Image.fromarray(last_frame)
                            img.save(str(output_image_path))
                            return output_image_path
                        except Exception as e:
                            st.error(f"截取视频尾帧失败: {e}")
                            return None

                    # 辅助函数：拼接视频
                    def concatenate_videos(video_paths, output_path):
                        try:
                            clips = [VideoFileClip(str(path)) for path in video_paths]
                            final_clip = concatenate_videoclips(clips)
                            final_clip.write_videofile(str(output_path), codec='libx264', audio_codec='aac')
                            final_clip.close()
                            return output_path
                        except Exception as e:
                            st.error(f"视频拼接失败: {e}")
                            return None

                    # 辅助函数：调整视频播放速度以匹配音频时长
                    def adjust_video_speed(video_path, target_duration, output_path):
                        try:
                            clip = VideoFileClip(str(video_path))
                            current_duration = clip.duration
                            
                            # 计算需要的速度调整比例
                            speed_factor = current_duration / target_duration
                            
                            # 使用ffmpeg命令行工具调整视频速度（最可靠的方法）
                            import subprocess
                            
                            # 使用ffmpeg的atempo滤镜调整速度
                            result = subprocess.run([
                                'ffmpeg', '-i', str(video_path),
                                '-filter:a', f'atempo={speed_factor}',
                                '-filter:v', f'setpts={1/speed_factor}*PTS',
                                str(output_path), '-y'
                            ], capture_output=True, text=True)
                            
                            clip.close()
                            
                            if result.returncode == 0:
                                return output_path
                            else:
                                st.error(f"ffmpeg速度调整失败: {result.stderr}")
                                return None
                        except Exception as e:
                            st.error(f"调整视频速度失败: {e}")
                            return None

                    # 修改视频生成函数来处理音视频时长调整（通过调整播放速度）
                    def generate_scene_video_with_audio_adjustment(video_prompt, image_path, audio_path, index):
                        """生成场景视频并通过调整播放速度匹配音频时长"""
                        try:
                            # 步骤1：先生成原始视频
                            video_path, video_url = generate_scene_video(video_prompt, image_path, index)
                            if not video_path:
                                return None, None
                            
                            # 获取音视频时长
                            video_duration = get_video_duration(video_path)
                            audio_duration = get_audio_duration(audio_path)
                            
                            if video_duration is None or audio_duration is None:
                                return video_path, video_url
                            
                            # 如果视频时长与音频时长一致，直接返回
                            if abs(video_duration - audio_duration) < 0.1:  # 允许0.1秒的误差
                                return video_path, video_url
                            
                            # 步骤2：调整视频播放速度以匹配音频时长
                            final_video_path = VIDEO_DIR / f"分镜视频_{index+1}_adjusted.mp4"
                            result = adjust_video_speed(video_path, audio_duration, final_video_path)
                            
                            if result:
                                st.success(f"视频速度已调整：原时长 {video_duration:.2f}s → 新时长 {audio_duration:.2f}s")
                                return result, video_url
                            else:
                                st.error("视频速度调整失败")
                                return video_path, video_url
                            
                        except Exception as e:
                            st.error(f"音视频时长调整失败: {e}")
                            return video_path, video_url
                    if image_path.exists() and prompt_path.exists() and audio_path.exists():
                        video_prompt = read_file(prompt_path)
                        with st.spinner(f"正在生成场景 {i+1} 的视频并调整时长..."):
                            video_path, video_url = generate_scene_video_with_audio_adjustment(video_prompt, image_path, audio_path, i)
                            if video_path:
                                st.session_state.scene_videos[i] = video_path
                                st.success(f"场景 {i+1} 视频生成成功！")
                            else:
                                st.error(f"场景 {i+1} 视频生成失败")
                    else:
                        st.warning("请先生成图片、视频Prompt和音频")
                
                # 显示视频（优先显示session state中的，如果没有则显示文件中的）
                video_path = VIDEO_DIR / f"分镜视频_{i+1}.mp4"
                if i in st.session_state.scene_videos:
                    st.video(str(st.session_state.scene_videos[i]))
                elif video_path.exists():
                    st.video(str(video_path))
                
                # 音视频合成
                if st.button(f"音视频合成 {i+1}", key=f"concatenate_av_{i}"):
                    video_path = VIDEO_DIR / f"分镜视频_{i+1}.mp4"
                    audio_path = AUDIO_DIR / f"分镜音频_{i+1}.wav"
                    if video_path.exists() and audio_path.exists():
                        with st.spinner(f"正在合成场景 {i+1} 的音视频..."):
                            av_path = concatenate_audio_video(video_path, audio_path, i)
                            if av_path:
                                st.session_state.scene_avs[i] = av_path
                                st.success(f"场景 {i+1} 音视频合成成功！")
                            else:
                                st.error(f"场景 {i+1} 音视频合成失败")
                    else:
                        st.warning("请先生成视频和音频")
                
                # 显示音视频
                av_path = AV_DIR / f"音视频_{i+1}.mp4"
                if av_path.exists():
                    st.video(str(av_path))
                
                st.divider()
    
    # 步骤八：视频拼接
    if st.session_state.extracted_data:
        st.header("步骤八：视频拼接")
        if st.button("拼接视频", key="concatenate_videos"):
            with st.spinner("正在拼接所有视频..."):
                final_video_path = concatenate_all_videos()
                if final_video_path:
                    st.success("视频拼接成功！")
                    st.video(str(final_video_path))
                    with open(final_video_path, 'rb') as f:
                        video_data = f.read()
                    st.download_button(
                        label="下载拼接视频",
                        data=video_data,
                        file_name="拼接视频.mp4",
                        mime="video/mp4"
                    )
                else:
                    st.error("视频拼接失败")

if __name__ == "__main__":
    main()

