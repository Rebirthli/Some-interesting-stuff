import requests
import json
from mcp.server.fastmcp import FastMCP

mcp = FastMCP('BeiJing Current Time MCP Server')

@mcp.tool(description="Used to directly obtain the current Beijing time")
def get_current_Beijing_time():
    url = "http://quan.suning.com/getSysTime.do"
    response = requests.get(url=url)
    data = json.loads(response.text)
    Normal_Time = data['sysTime2']
    return f'''
    code: {response.status_code}, 
    response: {response.text}, 
    当前时间是: {Normal_Time}
    '''
