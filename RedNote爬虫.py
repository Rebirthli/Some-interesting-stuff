import requests
from lxml import html

url = "The URL of the Xiaohongshu video you want"
html_content = requests.get(url).content
tree = html.fromstring(html_content)
video_link = tree.xpath('//meta[@name="og:video"]/@content')[0]
video_keywords = "关键字:" + tree.xpath('//meta[@name="keywords"]/@content')[0]
video_title = "标题:" + tree.xpath('//meta[@name="og:title"]/@content')[0].split(" ")[0].split("#")[0]
video_time = "视频时长:" + tree.xpath('//meta[@name="og:videotime"]/@content')[0]
video_videoquality = "画质:" + tree.xpath('//meta[@name="og:videoquality"]/@content')[0]
print(video_title)
print(video_time)
print(video_keywords)
print(video_videoquality)
print(video_link)
# 下载视频
response = requests.get(video_link, stream=True)
filename = "测试.mp4"
with open(filename, 'wb') as file:
    for chunk in response.iter_content(chunk_size=8192):
        file.write(chunk)
print(f"视频已下载为 {filename}")