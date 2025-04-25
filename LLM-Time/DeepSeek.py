import os
import time
import json
import statistics
import argparse
from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI

#加载环境变量中的API密钥
load_dotenv()
api_key = os.getenv("DEEPSEEK_API_KEY")

# 设置代理
os.environ["http_proxy"] = "http://localhost:7890"
os.environ["https_proxy"] = "http://localhost:7890"

# 初始化OpenAI客户端
client = OpenAI(
    api_key=api_key,
    base_url="https://api.deepseek.com"  # DEEPSEEK API的基础URL
)

# 默认测试参数
DEFAULT_PROMPTS = [
    "解释一下量子计算的基本原理",
    "写一个简短的Python函数来计算斐波那契数列",
    "分析人工智能在医疗领域的应用前景",
    "描述全球气候变化的主要原因和可能的解决方案",
    "解释区块链技术的工作原理及其在金融领域的应用"
]

DEFAULT_MODELS = ["deepseek-chat"]

class DeepSeekPerformanceTester:
    def __init__(self, models=None, prompts=None, runs=3, output_dir="results"):
        self.models = models or DEFAULT_MODELS
        self.prompts = prompts or DEFAULT_PROMPTS
        self.num_runs = runs
        self.output_dir = output_dir
        
        # 创建输出目录
        os.makedirs(output_dir, exist_ok=True)
        
        # 结果存储
        self.results = {}
        
    def run_tests(self):
        """运行所有测试"""
        for model in self.models:
            print(f"\n===== 测试模型: {model} =====")
            self.results[model] = {
                "tokens_per_second": [],
                "first_token_latency": [],
                "normalized_latency": [],
                "prompt_results": {}
            }
            
            for i, prompt in enumerate(self.prompts):
                print(f"\n提示 {i+1}/{len(self.prompts)}: {prompt[:30]}...")
                prompt_results = {
                    "prompt": prompt,
                    "runs": []
                }
                
                for run in range(self.num_runs):
                    print(f"  运行 {run+1}/{self.num_runs}")
                    run_result = self.test_single_prompt(model, prompt)
                    prompt_results["runs"].append(run_result)
                    
                    # 添加到总结果
                    self.results[model]["tokens_per_second"].append(run_result["tokens_per_second"])
                    self.results[model]["first_token_latency"].append(run_result["first_token_latency"])
                    self.results[model]["normalized_latency"].append(run_result["normalized_latency"])
                    
                    # # 在运行之间添加短暂的暂停，以避免API限制
                    # time.sleep(1)
                
                self.results[model]["prompt_results"][f"prompt_{i+1}"] = prompt_results
            
            # 计算每个模型的平均值
            self.calculate_model_averages(model)
    
    def test_single_prompt(self, model, prompt):
        """测试单个提示的性能"""
        # 记录开始时间
        start_time = time.time()
        
        # 发送请求并获取流式响应
        first_token_received = False
        first_token_time = None
        total_tokens = 0
        response_text = ""
        
        try:
            # 增加超时设置
            stream = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                stream=True,
                timeout=60  # 添加超时参数
            )
            
            # 设置最大等待时间
            max_wait_time = 120  # 秒
            stream_start_time = time.time()
            
            for chunk in stream:
                # 检查是否超过最大等待时间
                if time.time() - stream_start_time > max_wait_time:
                    print(f"    警告: 流式响应超过最大等待时间 {max_wait_time}秒，强制结束")
                    break
                    
                if not first_token_received and chunk.choices[0].delta.content:
                    first_token_time = time.time()
                    first_token_latency = first_token_time - start_time
                    first_token_received = True
                
                # 计算生成的token数并收集响应
                if chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    response_text += content
                    total_tokens += 1
        
        except Exception as e:
            print(f"错误: {e}")
            return {
                "error": str(e),
                "tokens_per_second": 0,
                "first_token_latency": 0,
                "normalized_latency": 0,
                "total_tokens": 0,
                "total_time": 0,
                "response": ""
            }
        
        # 记录结束时间
        end_time = time.time()
        
        # 计算指标
        total_time = end_time - start_time
        tokens_per_second = total_tokens / total_time if total_time > 0 else 0
        normalized_latency = total_time / total_tokens if total_tokens > 0 else 0
        
        print(f"    生成的tokens: {total_tokens}")
        print(f"    总时间: {total_time:.2f}秒")
        print(f"    首token延迟: {first_token_latency:.4f}秒")
        print(f"    tokens/s: {tokens_per_second:.2f}")
        print(f"    Normalized Latency: {normalized_latency:.4f}秒/token")
        
        return {
            "tokens_per_second": tokens_per_second,
            "first_token_latency": first_token_latency,
            "normalized_latency": normalized_latency,
            "total_tokens": total_tokens,
            "total_time": total_time,
            "response": response_text
        }
    
    def calculate_model_averages(self, model):
        """计算模型的平均性能指标"""
        model_results = self.results[model]
        
        model_results["avg_tokens_per_second"] = statistics.mean(model_results["tokens_per_second"])
        model_results["avg_first_token_latency"] = statistics.mean(model_results["first_token_latency"])
        model_results["avg_normalized_latency"] = statistics.mean(model_results["normalized_latency"])
        
        # 如果有足够的样本，计算标准差
        if len(model_results["tokens_per_second"]) > 1:
            model_results["std_tokens_per_second"] = statistics.stdev(model_results["tokens_per_second"])
            model_results["std_first_token_latency"] = statistics.stdev(model_results["first_token_latency"])
            model_results["std_normalized_latency"] = statistics.stdev(model_results["normalized_latency"])
        else:
            model_results["std_tokens_per_second"] = 0
            model_results["std_first_token_latency"] = 0
            model_results["std_normalized_latency"] = 0
    
    def print_summary(self):
        """打印测试结果摘要"""
        print("\n\n===== 性能测试摘要 =====")
        print(f"测试提示数量: {len(self.prompts)}")
        print(f"每个提示运行次数: {self.num_runs}")
        print(f"总运行次数: {len(self.prompts) * self.num_runs * len(self.models)}")
        
        for model in self.models:
            print(f"\n----- 模型: {model} -----")
            model_results = self.results[model]
            
            print(f"平均 tokens/s: {model_results['avg_tokens_per_second']:.2f} ± {model_results.get('std_tokens_per_second', 0):.2f}")
            print(f"平均首token延迟: {model_results['avg_first_token_latency']:.4f} ± {model_results.get('std_first_token_latency', 0):.4f}秒")
            print(f"平均Normalized Latency: {model_results['avg_normalized_latency']:.4f} ± {model_results.get('std_normalized_latency', 0):.4f}秒/token")
    
    def save_results(self):
        """保存测试结果到JSON文件"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = os.path.join(self.output_dir, f"DeepSeek_performance_test_{timestamp}.json")
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(self.results, f, ensure_ascii=False, indent=2)
        
        print(f"\n结果已保存到: {filename}")
        return filename

def main():
    parser = argparse.ArgumentParser(description='DeepSeek模型性能测试工具')
    parser.add_argument('--models', nargs='+', default=DEFAULT_MODELS, 
                        help='要测试的模型列表，例如 qwen-max qwen-plus')
    parser.add_argument('--runs', type=int, default=3, 
                        help='每个提示运行的次数')
    parser.add_argument('--prompts-file', type=str, 
                        help='包含测试提示的JSON文件路径')
    parser.add_argument('--output-dir', type=str, default='DeepSeek-results', 
                        help='结果输出目录')
    parser.add_argument('--timeout', type=int, default=120,
                        help='请求超时时间(秒)')
    
    args = parser.parse_args()
    
    # 如果提供了提示文件，从文件加载提示
    prompts = DEFAULT_PROMPTS
    if args.prompts_file:
        try:
            with open(args.prompts_file, 'r', encoding='utf-8') as f:
                prompts = json.load(f)
        except Exception as e:
            print(f"无法加载提示文件: {e}")
            return
    
    # 初始化测试器
    tester = DeepSeekPerformanceTester(
        models=args.models,
        prompts=prompts,
        runs=args.runs,
        output_dir=args.output_dir
    )
    
    # 运行测试
    print("开始DeepSeek模型性能测试...")
    tester.run_tests()
    tester.print_summary()
    tester.save_results()

if __name__ == "__main__":
    main()