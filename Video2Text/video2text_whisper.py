import os
import re
import time
import asyncio
from pathlib import Path
from moviepy.editor import VideoFileClip
import whisper
from opencc import OpenCC
from tqdm import tqdm
import concurrent.futures

# 添加ffmpeg路径配置（Windows需要）
os.environ["IMAGEIO_FFMPEG_EXE"] = "<Your ffmpeg path>"

# 创建输出目录
OUTPUT_DIR = "Oral_content"
if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)

# 设置最大并发数
MAX_CONCURRENT_TASKS = 3

def sanitize_filename(filename):
    """清理文件名，移除非法字符"""
    return re.sub(r'[<>:"/\\|?*]', '', filename)

async def process_video(video_path, semaphore):
    """处理单个视频文件"""
    async with semaphore:  # 使用信号量控制并发
        try:
            # 获取视频文件名（不含扩展名）作为标题
            video_filename = os.path.basename(video_path)
            video_title = os.path.splitext(video_filename)[0]
            safe_title = sanitize_filename(video_title)
            
            print(f"\n开始处理视频: {video_filename}")
            
            # 1. 将视频转换为音频
            audio_path = await convert_video_to_audio(video_path)
            
            # 2. 使用Whisper进行语音转文字
            transcription = await transcribe_audio(audio_path)
            print("\n转录文本片段:")
            print(transcription[:200] + "..." if len(transcription) > 200 else transcription)
            
            # 3. 保存转录文本到Oral_content目录
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            text_filename = os.path.join(OUTPUT_DIR, f"transcript_{timestamp}_{safe_title}.txt")
            with open(text_filename, 'w', encoding='utf-8') as f:
                f.write(transcription)
            print(f"\n转录文本已保存到 {text_filename}")
            
            # 4. 清理临时文件（只删除生成的音频文件，保留原始视频）
            try:
                os.remove(audio_path)
                print("临时音频文件清理完成")
            except Exception as e:
                print(f"清理临时音频文件时发生错误: {str(e)}")
                
            return True
        except Exception as e:
            print(f"处理视频 {video_path} 时发生错误: {str(e)}")
            return False

async def convert_video_to_audio(video_path):
    """将视频转换为音频"""
    loop = asyncio.get_event_loop()
    try:
        audio_path = video_path.replace('.mp4', '.mp3')
        print("开始转换视频到音频...")
        
        # 使用run_in_executor来异步执行CPU密集型操作
        def _convert():
            video = VideoFileClip(video_path)
            if video.audio is None:
                video.close()
                raise Exception("视频文件没有音轨")
            
            # 获取视频时长
            duration = video.duration
            print(f"视频总时长: {duration:.2f}秒")
            
            # 写入音频文件
            video.audio.write_audiofile(audio_path, 
                                      codec='libmp3lame',
                                      verbose=True,
                                      logger=None)
            video.close()
            return audio_path
        
        # 使用线程池执行器
        executor = concurrent.futures.ThreadPoolExecutor()
        result = await loop.run_in_executor(executor, _convert)
        print(f"音频转换完成: {audio_path}")
        return result
    except Exception as e:
        raise Exception(f"转换音频时发生错误: {str(e)}")

async def transcribe_audio(audio_path):
    """使用Whisper模型将音频转换为文字"""
    loop = asyncio.get_event_loop()
    try:
        print("开始转录音频...")
        
        # 使用run_in_executor来异步执行CPU密集型操作
        def _transcribe():
            model = whisper.load_model("large")
            
            # 创建转换器
            cc = OpenCC('t2s')
            
            print("正在转录音频，这可能需要几分钟...")
            result = model.transcribe(audio_path, language="zh")
            
            # 将繁体转换为简体
            simplified_text = cc.convert(result["text"])
            return simplified_text
        
        # 使用线程池执行器
        executor = concurrent.futures.ThreadPoolExecutor()
        result = await loop.run_in_executor(executor, _transcribe)
        print("音频转录完成")
        return result
    except Exception as e:
        raise Exception(f"转录音频时发生错误: {str(e)}")

async def process_videos_in_folder(folder_path):
    """处理文件夹中的所有MP4视频文件"""
    try:
        # 确保文件夹路径存在
        if not os.path.exists(folder_path) or not os.path.isdir(folder_path):
            raise Exception(f"文件夹 {folder_path} 不存在或不是一个有效的目录")
        
        # 获取所有MP4文件
        video_files = [os.path.join(folder_path, f) for f in os.listdir(folder_path) 
                      if f.lower().endswith('.mp4')]
        
        if not video_files:
            print(f"在文件夹 {folder_path} 中没有找到MP4文件")
            return
        
        print(f"在文件夹 {folder_path} 中找到 {len(video_files)} 个MP4文件")
        
        # 创建信号量控制并发数量
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_TASKS)
        
        # 创建任务列表
        tasks = [process_video(video_file, semaphore) for video_file in video_files]
        
        # 并发执行所有任务
        print(f"开始并发处理视频，最大并发数: {MAX_CONCURRENT_TASKS}")
        results = await asyncio.gather(*tasks)
        
        # 统计处理结果
        success_count = sum(1 for result in results if result)
        fail_count = len(results) - success_count
        print(f"\n处理完成: 成功 {success_count} 个, 失败 {fail_count} 个")
    
    except Exception as e:
        print(f"处理文件夹时发生错误: {str(e)}")

async def main():
    try:
        # 获取视频文件夹路径
        folder_path = input("请输入包含MP4视频文件的文件夹路径: ").strip()
        if not folder_path:
            folder_path = os.path.dirname(os.path.abspath(__file__))  # 默认使用当前脚本所在目录
            print(f"使用默认文件夹路径: {folder_path}")
        
        # 处理文件夹中的视频
        await process_videos_in_folder(folder_path)
            
    except Exception as e:
        print(f"程序执行出错: {str(e)}")
    finally:
        print("程序执行结束")

if __name__ == "__main__":
    # 使用asyncio运行主函数
    asyncio.run(main())