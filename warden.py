import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import requests
import json
import threading
from datetime import datetime
import pytz
import os
import queue
import time
from eth_account import Account
from eth_account.messages import encode_defunct

class WardenGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Warden 小号保活工具 by晚风(x.com/pl_wanfeng)")
        self.root.geometry("1000x700")
        self.root.configure(bg='#f5f5f5')  # 设置主窗口背景色
        
        # 设置优化的主题样式
        self.style = ttk.Style()
        
        # 尝试使用不同的主题，避免黑色显示问题
        available_themes = self.style.theme_names()
        if 'vista' in available_themes:
            self.style.theme_use('vista')
        elif 'winnative' in available_themes:
            self.style.theme_use('winnative')
        elif 'aqua' in available_themes:
            self.style.theme_use('aqua')
        else:
            self.style.theme_use('default')
        
        # 配置样式，避免黑色背景问题
        self.style.configure('TFrame', background='#f5f5f5', relief='flat')
        self.style.configure('TLabel', background='#f5f5f5', foreground='#333333')
        self.style.configure('TButton', background='#e8e8e8', foreground='#333333', 
                           focuscolor='none', borderwidth=1, relief='raised')
        self.style.configure('TLabelFrame', background='#f5f5f5', foreground='#333333')
        self.style.configure('TLabelFrame.Label', background='#f5f5f5', foreground='#333333')
        self.style.configure('TCheckbutton', background='#f5f5f5', foreground='#333333')
        self.style.configure('TEntry', relief='sunken', borderwidth=1)
        
        # 配置树状视图样式
        self.style.configure('Treeview', background='#ffffff', foreground='#333333',
                           fieldbackground='#ffffff', borderwidth=1, relief='sunken')
        self.style.configure('Treeview.Heading', background='#e8e8e8', foreground='#333333',
                           relief='raised', borderwidth=1)
        # 配置选中状态的颜色
        self.style.map('Treeview', 
                      background=[('selected', '#316AC5')],
                      foreground=[('selected', '#ffffff')])
        
        # 配置滚动条样式
        self.style.configure('Vertical.TScrollbar', background='#e8e8e8', 
                           troughcolor='#f5f5f5', borderwidth=1, relief='sunken')
        
        self.tokens = []
        self.user_info = {}  # 存储每个token的用户信息 {token: {tokenName, pointsTotal, createdAt}}
        
        # 创建线程安全的消息队列
        self.message_queue = queue.Queue()
        self.running_tasks = 0  # 跟踪正在运行的任务数量
        
        self.create_widgets()
        self.load_tokens()
        
        # 启动消息处理定时器
        self.process_queue_messages()
        
        # 确保界面正确渲染
        self.root.update_idletasks()
    
    def create_widgets(self):
        # 主框架
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # 账户列表框架
        accounts_frame = ttk.LabelFrame(main_frame, text="账户列表", padding="10")
        accounts_frame.grid(row=1, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        
        # 状态说明
        status_info = ttk.Label(accounts_frame, text="状态说明: 待处理 | 成功 | 已完成 | Token失效 | 失败 | 错误 | 未知", 
                               foreground='#666666', font=('Arial', 8))
        status_info.grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 5))
        
        # 创建树状视图来显示账户
        self.tree = ttk.Treeview(accounts_frame, columns=('index', 'token_preview', 'token_name', 'points_total', 'created_at', 'status'), 
                                show='headings', height=10)
        self.tree.heading('index', text='序号')
        self.tree.heading('token_preview', text='Token预览')
        self.tree.heading('token_name', text='代币名称')
        self.tree.heading('points_total', text='积分数量')
        self.tree.heading('created_at', text='创建时间')
        self.tree.heading('status', text='状态')
        
        self.tree.column('index', width=50, minwidth=50)
        self.tree.column('token_preview', width=200, minwidth=150)
        self.tree.column('token_name', width=100, minwidth=80)
        self.tree.column('points_total', width=80, minwidth=60)
        self.tree.column('created_at', width=120, minwidth=100)
        self.tree.column('status', width=100, minwidth=80)
        
        # 绑定选择事件，确保选择状态正确显示
        self.tree.bind('<<TreeviewSelect>>', self.on_tree_select)
        
        # 滚动条
        scrollbar = ttk.Scrollbar(accounts_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        self.tree.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        scrollbar.grid(row=1, column=1, sticky=(tk.N, tk.S))
        
        # 按钮框架
        button_frame = ttk.Frame(accounts_frame)
        button_frame.grid(row=2, column=0, columnspan=2, pady=(10, 0), sticky=tk.W)
        
        # 第一行：代理设置 + 代理说明
        proxy_row = ttk.Frame(button_frame)
        proxy_row.grid(row=0, column=0, columnspan=3, sticky=tk.W, pady=(0, 8))
        
        self.proxy_enabled = tk.BooleanVar()
        proxy_check = ttk.Checkbutton(proxy_row, text="使用代理 (从proxies.txt文件读取)", 
                                     variable=self.proxy_enabled)
        proxy_check.pack(side=tk.LEFT)
        
        proxy_info = ttk.Label(proxy_row, text="代理格式: http://user:pass@ip:port 或 http://ip:port，每行一个代理", 
                               foreground='#666666', font=('Arial', 8))
        proxy_info.pack(side=tk.LEFT, padx=(20, 0))
        
        # 第二行：功能按钮 + 统计信息
        action_row = ttk.Frame(button_frame)
        action_row.grid(row=1, column=0, columnspan=3, sticky=tk.W)
        
        # 左侧按钮组容器 - 前三个按钮紧挨着，完全贴左
        left_button_group = ttk.Frame(action_row)
        left_button_group.pack(side=tk.LEFT)
        
        ttk.Button(left_button_group, text="钱包认证获取Token", 
                  command=self.start_wallet_auth).pack(side=tk.LEFT, padx=(0, 0))
        ttk.Button(left_button_group, text="加载用户信息", 
                  command=self.load_user_info).pack(side=tk.LEFT, padx=(0, 0))
        ttk.Button(left_button_group, text="查看选中账户", 
                  command=self.view_selected_account).pack(side=tk.LEFT, padx=(0, 0))
        
        # 右侧按钮组 - 一键完成任务和统计信息
        right_group = ttk.Frame(action_row)
        right_group.pack(side=tk.LEFT, padx=(40, 0))
        
        ttk.Button(right_group, text="一键完成任务", 
                  command=self.execute_all_tasks).pack(side=tk.LEFT, padx=(0, 15))
        
        self.stats_label = ttk.Label(right_group, text="", foreground='#666666', font=('Arial', 8))
        self.stats_label.pack(side=tk.LEFT)
        
        accounts_frame.columnconfigure(0, weight=1)
        accounts_frame.rowconfigure(1, weight=1)
        
        # 日志框架
        log_frame = ttk.LabelFrame(main_frame, text="操作日志", padding="10")
        log_frame.grid(row=2, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=8, width=80,
                                                bg='#ffffff', fg='#333333', 
                                                insertbackground='#333333',
                                                selectbackground='#316AC5',
                                                selectforeground='#ffffff',
                                                font=('Consolas', 9),
                                                relief='sunken', borderwidth=1)
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # 日志操作按钮
        log_button_frame = ttk.Frame(log_frame)
        log_button_frame.grid(row=1, column=0, sticky=tk.W, pady=(5, 0))
        
        ttk.Button(log_button_frame, text="清空日志", 
                  command=self.clear_log).grid(row=0, column=0, padx=(0, 10))
        
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        
        # 配置主窗口的网格权重
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(1, weight=1)
        main_frame.rowconfigure(2, weight=1)
        
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
    

    
    def load_tokens(self):
        """从tokens.txt文件加载token"""
        try:
            if os.path.exists('tokens.txt'):
                with open('tokens.txt', 'r', encoding='utf-8') as f:
                    self.tokens = [line.strip() for line in f.readlines() if line.strip()]
                self.refresh_accounts()
                self._safe_log_message(f"成功加载 {len(self.tokens)} 个Token")
            else:
                self._safe_log_message("未找到tokens.txt文件，请先创建该文件")
        except Exception as e:
            self._safe_log_message(f"加载Token文件失败: {str(e)}")
    

    
    def refresh_accounts(self):
        """刷新账户列表显示"""
        # 清空现有项目
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        # 添加新项目
        for i, token in enumerate(self.tokens):
            token_preview = token[:50] + "..." if len(token) > 50 else token
            
            # 获取用户信息
            user_data = self.user_info.get(token, {})
            token_name = user_data.get('tokenName', '-')
            points_total = user_data.get('pointsTotal', '-')
            created_at = user_data.get('createdAt', '-')
            
            self.tree.insert('', 'end', values=(i+1, token_preview, token_name, points_total, created_at, "待处理"))
        
        # 更新统计信息
        self.update_stats()
        
        # 刷新界面显示
        self.refresh_ui()
    
    def view_selected_account(self):
        """查看选中的账户详情"""
        selected_item = self.tree.selection()
        if not selected_item:
            messagebox.showwarning("警告", "请先选择一个账户")
            return
        
        item_values = self.tree.item(selected_item[0])['values']
        account_index = int(item_values[0]) - 1
        
        if 0 <= account_index < len(self.tokens):
            self.show_account_detail(account_index)
    
    def show_account_detail(self, account_index):
        """显示账户详情窗口"""
        detail_window = tk.Toplevel(self.root)
        detail_window.title(f"账户详情 - {account_index + 1}")
        detail_window.geometry("600x400")
        detail_window.configure(bg='#f5f5f5')  # 设置窗口背景色
        
        # 账户信息框架
        info_frame = ttk.LabelFrame(detail_window, text="账户信息", padding="10")
        info_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Token显示
        ttk.Label(info_frame, text="Token:").pack(anchor=tk.W)
        token_text = scrolledtext.ScrolledText(info_frame, height=10, width=70,
                                             bg='#ffffff', fg='#333333',
                                             insertbackground='#333333',
                                             selectbackground='#316AC5',
                                             selectforeground='#ffffff',
                                             font=('Consolas', 9),
                                             relief='sunken', borderwidth=1)
        token_text.pack(fill=tk.BOTH, expand=True, pady=(5, 10))
        token_text.insert(tk.END, self.tokens[account_index])
        token_text.config(state=tk.DISABLED)
        
        # 操作按钮
        button_frame = ttk.Frame(info_frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Button(button_frame, text="执行任务", 
                  command=lambda: self.execute_single_task(account_index)).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(button_frame, text="关闭", 
                  command=detail_window.destroy).pack(side=tk.RIGHT)
    
    def get_beijing_time(self):
        """获取当前北京时间，格式为ISO 8601"""
        beijing_tz = pytz.timezone('Asia/Shanghai')
        beijing_time = datetime.now(beijing_tz)
        return beijing_time.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
    
    def get_proxies(self):
        """从proxies.txt文件获取代理设置"""
        if not self.proxy_enabled.get():
            return None
        
        try:
            if not os.path.exists('proxies.txt'):
                self.safe_log_message("未找到proxies.txt文件，请创建该文件并添加代理地址")
                return None
            
            with open('proxies.txt', 'r', encoding='utf-8') as f:
                proxy_lines = [line.strip() for line in f.readlines() if line.strip() and not line.startswith('#')]
            
            if not proxy_lines:
                self.safe_log_message("proxies.txt文件为空或没有有效的代理地址")
                return None
            
            # 随机选择一个代理
            import random
            selected_proxy = random.choice(proxy_lines)
            
            # 构造代理字典
            proxies = {
                'http': selected_proxy,
                'https': selected_proxy
            }
            
            return proxies
            
        except Exception as e:
            self.safe_log_message(f"读取代理文件失败: {str(e)}")
            return None
    
    def execute_single_task(self, account_index):
        """执行单个账户的任务"""
        if account_index >= len(self.tokens):
            self.safe_log_message(f"账户索引 {account_index + 1} 超出范围")
            return
        
        def task():
            try:
                token = self.tokens[account_index]
                timestamp = self.get_beijing_time()
                
                # 构建请求数据
                headers = {
                    'Host': 'api.app.wardenprotocol.org',
                    'Connection': 'keep-alive',
                    'sec-ch-ua-platform': '"macOS"',
                    'Authorization': f'Bearer {token}',
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36',
                    'sec-ch-ua': '"Google Chrome";v="137", "Chromium";v="137", "Not/A)Brand";v="24"',
                    'Content-Type': 'application/json',
                    'sec-ch-ua-mobile': '?0',
                    'Accept': '*/*',
                    'Origin': 'https://app.wardenprotocol.org',
                    'Sec-Fetch-Site': 'same-site',
                    'Sec-Fetch-Mode': 'cors',
                    'Sec-Fetch-Dest': 'empty',
                    'Referer': 'https://app.wardenprotocol.org/',
                    'Accept-Encoding': 'gzip, deflate, br, zstd',
                    'Accept-Language': 'zh-CN,zh;q=0.9'
                }
                
                data = {
                    "activityType": "CHAT_INTERACTION",
                    "metadata": {
                        "action": "user_chat",
                        "message_length": 20,
                        "timestamp": timestamp
                    }
                }
                
                url = 'https://api.app.wardenprotocol.org/api/tokens/activity'
                proxies = self.get_proxies()
                
                self.safe_log_message(f"账户 {account_index + 1} 开始执行任务...")
                
                response = requests.post(url, headers=headers, json=data, 
                                       proxies=proxies, timeout=30)
                
                # 检查HTTP状态码：200或201都可能表示成功
                if response.status_code in [200, 201]:
                    try:
                        response_data = response.json()
                        
                        # 检查是否包含activityId和newTokenPrice，表示AI交互任务完成
                        if 'activityId' in response_data and 'newTokenPrice' in response_data:
                            self.safe_log_message(f"账户 {account_index + 1} AI交互任务完成 - HTTP {response.status_code} - activityId: {response_data['activityId']}, newTokenPrice: {response_data['newTokenPrice']}")
                            self.safe_update_status(account_index, "成功")
                        # 检查是否是今天已完成任务的返回
                        elif 'error' in response_data or 'message' in response_data:
                            error_msg = response_data.get('error', response_data.get('message', ''))
                            if 'today' in error_msg.lower() or 'already' in error_msg.lower() or '已完成' in error_msg:
                                self.safe_log_message(f"账户 {account_index + 1} AI对话已做")
                                self.safe_update_status(account_index, "已完成")
                            elif 'invalid access token' in error_msg.lower() or ('token' in error_msg.lower() and 'invalid' in error_msg.lower()):
                                self.safe_log_message(f"账户 {account_index + 1} Token已失效: {error_msg}")
                                self.safe_update_status(account_index, "Token失效")
                            else:
                                self.safe_log_message(f"账户 {account_index + 1} 返回错误: {error_msg}")
                                self.safe_update_status(account_index, "错误")
                        else:
                            # 其他返回内容
                            self.safe_log_message(f"账户 {account_index + 1} 返回内容: {json.dumps(response_data, ensure_ascii=False)}")
                            self.safe_update_status(account_index, "未知")
                    except json.JSONDecodeError:
                        # 返回的不是JSON格式
                        response_text = response.text
                        if '已完成' in response_text or 'already' in response_text.lower() or 'today' in response_text.lower():
                            self.safe_log_message(f"账户 {account_index + 1} AI对话已做")
                            self.safe_update_status(account_index, "已完成")
                        elif 'invalid access token' in response_text.lower() or ('token' in response_text.lower() and 'invalid' in response_text.lower()):
                            self.safe_log_message(f"账户 {account_index + 1} Token已失效: {response_text}")
                            self.safe_update_status(account_index, "Token失效")
                        else:
                            self.safe_log_message(f"账户 {account_index + 1} 返回文本: {response_text}")
                            self.safe_update_status(account_index, "未知")
                else:
                    self.safe_log_message(f"账户 {account_index + 1} 任务执行失败: HTTP {response.status_code} - {response.text}")
                    self.safe_update_status(account_index, "失败")
                    
            except Exception as e:
                self.safe_log_message(f"账户 {account_index + 1} 执行任务时发生错误: {str(e)}")
                self.safe_update_status(account_index, "错误")
            finally:
                # 通知任务完成
                self.message_queue.put({'type': 'task_complete'})
        
        # 在新线程中执行任务
        thread = threading.Thread(target=task, name=f"Task-{account_index}")
        thread.daemon = True
        thread.start()
    
    def execute_all_tasks(self):
        """一键执行所有账户的任务"""
        if not self.tokens:
            messagebox.showwarning("警告", "没有可用的Token，请检查tokens.txt文件")
            return
        
        # 检查是否有任务正在运行
        if self.running_tasks > 0:
            messagebox.showwarning("警告", f"还有 {self.running_tasks} 个任务正在执行中，请等待完成后再次尝试")
            return
        
        result = messagebox.askyesno("确认", f"确定要为所有 {len(self.tokens)} 个账户执行任务吗？")
        if result:
            self.safe_log_message("开始批量执行任务...")
            self.running_tasks = len(self.tokens)
            
            # 使用定时器逐个启动任务，避免同时创建太多线程
            def start_task_with_delay(index):
                if index < len(self.tokens):
                    self.execute_single_task(index)
                    # 下一个任务延迟0.5秒启动
                    if index + 1 < len(self.tokens):
                        self.root.after(500, lambda: start_task_with_delay(index + 1))
            
            # 开始第一个任务
            start_task_with_delay(0)
    
    def update_account_status(self, account_index, status):
        """更新账户状态显示"""
        for item in self.tree.get_children():
            item_values = self.tree.item(item)['values']
            if int(item_values[0]) - 1 == account_index:
                self.tree.item(item, values=(item_values[0], item_values[1], status))
                break
        self.update_stats()
        
        # 刷新界面
        self.refresh_ui()
    
    def update_stats(self):
        """更新统计信息"""
        if not hasattr(self, 'stats_label'):
            return
            
        stats = {
            '待处理': 0,
            '成功': 0,
            '已完成': 0,
            'Token失效': 0,
            '失败': 0,
            '错误': 0,
            '未知': 0
        }
        
        for item in self.tree.get_children():
            item_values = self.tree.item(item)['values']
            if len(item_values) > 5:
                status = item_values[5]  # 状态现在是第6列（索引5）
                if status in stats:
                    stats[status] += 1
        
        total = sum(stats.values())
        if total > 0:
            stats_text = f"总计: {total} | "
            stats_text += " | ".join([f"{k}: {v}" for k, v in stats.items() if v > 0])
            self.stats_label.config(text=stats_text)
    
    def on_tree_select(self, event):
        """处理树状视图选择事件"""
        # 确保选择状态正确显示，防止显示异常
        selection = self.tree.selection()
        if selection:
            # 刷新选中项的显示
            self.tree.update_idletasks()
    
    def log_message(self, message):
        """添加日志消息（已废弃，使用safe_log_message）"""
        # 为了兼容性保留此方法，但重定向到安全方法
        self.safe_log_message(message)
    
    def clear_log(self):
        """清空日志"""
        try:
            self.log_text.delete(1.0, tk.END)
            self._safe_log_message("日志已清空")
        except Exception as e:
            print(f"清空日志失败: {e}")
    
    def refresh_ui(self):
        """刷新界面显示，防止显示异常"""
        try:
            self.root.update_idletasks()
            self.tree.update_idletasks()
            self.log_text.update_idletasks()
        except:
            pass
    
    def process_queue_messages(self):
        """处理消息队列中的GUI更新请求（在主线程中执行）"""
        try:
            while True:
                message = self.message_queue.get_nowait()
                msg_type = message.get('type')
                
                if msg_type == 'log':
                    self._safe_log_message(message['text'])
                elif msg_type == 'status':
                    self._safe_update_status(message['account_index'], message['status'])
                elif msg_type == 'task_complete':
                    self.running_tasks -= 1
                    if self.running_tasks <= 0:
                        self._safe_log_message("所有任务执行完成")
                elif msg_type == 'reload_tokens':
                    # 在主线程中重新加载token
                    try:
                        self._safe_reload_tokens()
                        self._safe_log_message("Token列表已刷新，可以开始使用新获取的token执行任务")
                    except Exception as e:
                        self._safe_log_message(f"重新加载token失败: {str(e)}")
                elif msg_type == 'refresh_accounts':
                    # 在主线程中刷新账户列表
                    try:
                        self.refresh_accounts()
                        self._safe_log_message("账户列表已刷新，用户信息已更新")
                    except Exception as e:
                        self._safe_log_message(f"刷新账户列表失败: {str(e)}")
                        
        except queue.Empty:
            pass
        except Exception as e:
            print(f"处理队列消息时出错: {e}")
        
        # 每100ms检查一次队列
        self.root.after(100, self.process_queue_messages)
    
    def _safe_log_message(self, message):
        """线程安全的日志消息添加方法"""
        try:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            log_entry = f"[{timestamp}] {message}\n"
            self.log_text.insert(tk.END, log_entry)
            self.log_text.see(tk.END)
            self.log_text.update_idletasks()
        except Exception as e:
            print(f"日志更新错误: {e}")
    
    def _safe_update_status(self, account_index, status):
        """线程安全的状态更新方法"""
        try:
            for item in self.tree.get_children():
                item_values = self.tree.item(item)['values']
                if int(item_values[0]) - 1 == account_index:
                    # 更新状态列（保持其他列不变）
                    new_values = list(item_values)
                    new_values[5] = status  # 状态现在是第6列（索引5）
                    self.tree.item(item, values=tuple(new_values))
                    break
            self.update_stats()
            self.refresh_ui()
        except Exception as e:
            print(f"状态更新错误: {e}")
    
    def _safe_reload_tokens(self):
        """线程安全的重新加载token方法（在主线程中执行）"""
        try:
            if os.path.exists('tokens.txt'):
                with open('tokens.txt', 'r', encoding='utf-8') as f:
                    self.tokens = [line.strip() for line in f.readlines() if line.strip()]
                self.refresh_accounts()
                print(f"成功重新加载 {len(self.tokens)} 个Token")
            else:
                print("未找到tokens.txt文件")
        except Exception as e:
            print(f"重新加载Token文件失败: {str(e)}")
    
    def safe_log_message(self, message):
        """向队列发送日志消息（线程安全）"""
        try:
            self.message_queue.put({'type': 'log', 'text': message})
        except Exception as e:
            print(f"发送日志消息失败: {e}")
    
    def safe_update_status(self, account_index, status):
        """向队列发送状态更新请求（线程安全）"""
        try:
            self.message_queue.put({'type': 'status', 'account_index': account_index, 'status': status})
        except Exception as e:
            print(f"发送状态更新失败: {e}")
    
    # ==================== 用户信息获取相关方法 ====================
    
    def get_user_info(self, token):
        """获取单个token的用户信息"""
        try:
            url = 'https://api.app.wardenprotocol.org/api/tokens/user/me'
            
            headers = {
                'Host': 'api.app.wardenprotocol.org',
                'Connection': 'keep-alive',
                'sec-ch-ua-platform': '"macOS"',
                'Authorization': f'Bearer {token}',
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36',
                'sec-ch-ua': '"Google Chrome";v="137", "Chromium";v="137", "Not/A)Brand";v="24"',
                'Content-Type': 'application/json',
                'sec-ch-ua-mobile': '?0',
                'Accept': '*/*',
                'Origin': 'https://app.wardenprotocol.org',
                'Sec-Fetch-Site': 'same-site',
                'Sec-Fetch-Mode': 'cors',
                'Sec-Fetch-Dest': 'empty',
                'Referer': 'https://app.wardenprotocol.org/',
                'Accept-Encoding': 'gzip, deflate, br, zstd',
                'Accept-Language': 'zh-CN,zh;q=0.9',
                'If-None-Match': 'W/"130-W12Y5j5FF9RMoYw/zUo2mBbyOlc"'
            }
            
            proxies = self.get_proxies()
            
            response = requests.get(url, headers=headers, proxies=proxies, timeout=30)
            
            if response.status_code == 200:
                try:
                    user_data = response.json()
                    
                    # 从返回的数据结构中提取token信息
                    token_data = user_data.get('token', {})
                    
                    if not token_data:
                        self.safe_log_message(f"警告: 响应中未找到token对象，响应结构: {list(user_data.keys())}")
                        return None
                    
                    # 提取需要的信息
                    token_name = token_data.get('tokenName', '-')
                    points_total = token_data.get('pointsTotal', '-')
                    created_at = token_data.get('createdAt', '-')
                    
                    # 格式化创建时间 (转换为北京时间)
                    if created_at != '-':
                        try:
                            from datetime import datetime
                            import pytz
                            
                            # 解析UTC时间
                            dt_utc = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                            
                            # 转换为北京时间
                            beijing_tz = pytz.timezone('Asia/Shanghai')
                            dt_beijing = dt_utc.astimezone(beijing_tz)
                            
                            created_at = dt_beijing.strftime('%Y-%m-%d %H:%M')
                        except:
                            # 如果时间格式解析失败，保持原样
                            pass
                    
                    # 添加调试信息
                    self.safe_log_message(f"解析用户信息成功: tokenName={token_name}, pointsTotal={points_total}, createdAt={created_at}")
                    
                    return {
                        'tokenName': token_name,
                        'pointsTotal': points_total,
                        'createdAt': created_at
                    }
                    
                except json.JSONDecodeError:
                    self.safe_log_message(f"解析用户信息失败: 返回数据不是JSON格式 - {response.text}")
                    return None
            else:
                self.safe_log_message(f"获取用户信息失败: HTTP {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            self.safe_log_message(f"获取用户信息时发生错误: {str(e)}")
            return None
    
    def load_user_info(self):
        """加载所有token的用户信息"""
        if not self.tokens:
            messagebox.showwarning("警告", "没有可用的Token，请检查tokens.txt文件")
            return
        
        # 检查是否有任务正在运行
        if self.running_tasks > 0:
            messagebox.showwarning("警告", f"有任务正在执行中，请等待完成后再加载用户信息")
            return
        
        result = messagebox.askyesno("确认", f"确定要加载所有 {len(self.tokens)} 个账户的用户信息吗？")
        if result:
            self.safe_log_message("开始加载用户信息...")
            threading.Thread(target=self.batch_load_user_info, daemon=True).start()
    
    def batch_load_user_info(self):
        """批量加载用户信息（在子线程中运行）"""
        try:
            success_count = 0
            for i, token in enumerate(self.tokens):
                self.safe_log_message(f"正在加载账户 {i+1}/{len(self.tokens)} 的用户信息...")
                
                user_info = self.get_user_info(token)
                if user_info:
                    self.user_info[token] = user_info
                    success_count += 1
                    self.safe_log_message(f"账户 {i+1} 用户信息加载成功 - 代币: {user_info['tokenName']}, 积分: {user_info['pointsTotal']}, 创建时间: {user_info['createdAt']}")
                else:
                    self.safe_log_message(f"账户 {i+1} 用户信息加载失败")
                
                # 延迟避免请求过快
                time.sleep(1)
            
            self.safe_log_message(f"用户信息加载完成！成功加载 {success_count}/{len(self.tokens)} 个账户的信息")
            
            # 通知主线程刷新界面
            self.message_queue.put({'type': 'refresh_accounts'})
            
        except Exception as e:
            self.safe_log_message(f"批量加载用户信息时发生错误: {str(e)}")
            import traceback
            traceback.print_exc()
    
    # ==================== 钱包认证相关方法 ====================
    
    def start_wallet_auth(self):
        """启动钱包认证流程"""
        try:
            # 检查是否存在私钥文件
            if not os.path.exists('private_keys.txt'):
                messagebox.showerror("错误", "未找到private_keys.txt文件\n请创建该文件并添加您的私钥，每行一个私钥")
                return
            
            # 加载私钥
            private_keys = self.load_private_keys()
            if not private_keys:
                messagebox.showerror("错误", "private_keys.txt文件为空或格式错误\n请添加有效的私钥，每行一个")
                return
            
            # 确认对话框
            result = messagebox.askyesno("确认认证", 
                                       f"找到 {len(private_keys)} 个私钥\n"
                                       f"是否开始批量钱包认证？\n\n"
                                       f"注意：认证过程将获取token并保存到tokens.txt文件")
            if not result:
                return
            
            # 启动批量认证
            self.safe_log_message(f"开始批量钱包认证，共 {len(private_keys)} 个钱包...")
            
            # 创建并启动认证线程，添加异常处理
            auth_thread = threading.Thread(target=self.safe_batch_wallet_auth, args=(private_keys,), daemon=True)
            auth_thread.start()
            
        except Exception as e:
            self.safe_log_message(f"启动钱包认证失败: {str(e)}")
            messagebox.showerror("错误", f"启动钱包认证失败:\n{str(e)}")
    
    def load_private_keys(self):
        """从private_keys.txt文件加载私钥"""
        try:
            with open('private_keys.txt', 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            private_keys = []
            for i, line in enumerate(lines, 1):
                line = line.strip()
                if not line or line.startswith('#'):  # 跳过空行和注释行
                    continue
                
                # 验证私钥格式
                if len(line) == 64 and all(c in '0123456789abcdefABCDEF' for c in line):
                    private_keys.append(line)
                elif len(line) == 66 and line.startswith('0x') and all(c in '0123456789abcdefABCDEF' for c in line[2:]):
                    private_keys.append(line[2:])  # 移除0x前缀
                else:
                    self.safe_log_message(f"第{i}行私钥格式错误，已跳过: {line[:20]}...")
            
            return private_keys
        except Exception as e:
            self.safe_log_message(f"加载私钥文件失败: {str(e)}")
            return []
    
    def safe_batch_wallet_auth(self, private_keys):
        """安全的批量钱包认证包装器"""
        try:
            self.batch_wallet_auth(private_keys)
        except Exception as e:
            # 最外层异常处理，确保线程异常不会影响GUI
            self.safe_log_message(f"钱包认证线程发生未预期的错误: {str(e)}")
            import traceback
            print("钱包认证线程异常详情:")
            traceback.print_exc()
    
    def get_wallet_address(self, private_key):
        """根据私钥获取钱包地址"""
        try:
            if not private_key.startswith('0x'):
                private_key = '0x' + private_key
            account = Account.from_key(private_key)
            return account.address
        except Exception as e:
            self.safe_log_message(f"获取钱包地址失败: {str(e)}")
            return None
    
    def get_nonce(self, wallet_address):
        """获取nonce值（带重试机制）"""
        import random
        
        max_retries = 5
        base_delay = 3  # 基础延迟时间
        
        for attempt in range(max_retries):
            try:
                url = 'https://auth.privy.io/api/v1/siwe/init'
                
                # 生成随机的privy-ca-id，避免被识别为同一客户端
                import uuid
                random_ca_id = str(uuid.uuid4())
                self.safe_log_message(f"获取nonce时使用随机privy-ca-id: {random_ca_id[:8]}...")
                
                headers = {
                    'Content-Type': 'application/json',
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Origin': 'https://app.wardenprotocol.org',
                    'Referer': 'https://app.wardenprotocol.org/',
                    'Accept': 'application/json, text/plain, */*',
                    'Accept-Language': 'en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Cache-Control': 'no-cache',
                    'Pragma': 'no-cache',
                    'Sec-Fetch-Dest': 'empty',
                    'Sec-Fetch-Mode': 'cors',
                    'Sec-Fetch-Site': 'cross-site',
                    'privy-app-id': 'cm7f00k5c02tibel0m4o9tdy1',
                    'privy-ca-id': random_ca_id
                }
                
                payload = {"address": wallet_address}
                proxies = self.get_proxies()
                
                response = requests.post(url, json=payload, headers=headers, proxies=proxies, timeout=30)
                
                if response.status_code == 200:
                    response_data = response.json()
                    if 'nonce' in response_data:
                        return response_data['nonce']
                    else:
                        self.safe_log_message(f"响应中未找到nonce字段: {response_data}")
                        return None
                elif response.status_code == 429:
                    # 处理429错误，使用指数退避策略
                    if attempt < max_retries - 1:
                        # 计算延迟时间：基础延迟 * (2^尝试次数) + 随机时间
                        delay = base_delay * (2 ** attempt) + random.uniform(1, 3)
                        self.safe_log_message(f"获取nonce遇到限流(429)，{delay:.1f}秒后重试 (尝试 {attempt + 1}/{max_retries})")
                        time.sleep(delay)
                        continue
                    else:
                        self.safe_log_message(f"获取nonce失败，重试{max_retries}次后仍遇到限流，状态码: {response.status_code}, 响应: {response.text}")
                        return None
                else:
                    self.safe_log_message(f"获取nonce失败，状态码: {response.status_code}, 响应: {response.text}")
                    return None
                    
            except Exception as e:
                if attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt) + random.uniform(1, 3)
                    self.safe_log_message(f"获取nonce发生错误: {str(e)}，{delay:.1f}秒后重试 (尝试 {attempt + 1}/{max_retries})")
                    time.sleep(delay)
                    continue
                else:
                    self.safe_log_message(f"获取nonce时发生错误: {str(e)}")
                    return None
        
        return None
    
    def get_current_time_iso(self):
        """获取当前UTC时间的ISO格式"""
        utc_time = datetime.now(pytz.UTC)
        return utc_time.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
    
    def create_siwe_message(self, wallet_address, nonce):
        """创建SIWE消息"""
        issued_at = self.get_current_time_iso()
        
        message = f"""app.wardenprotocol.org wants you to sign in with your Ethereum account:
{wallet_address}

By signing, you are proving you own this wallet and logging in. This does not initiate a transaction or cost any fees.

URI: https://app.wardenprotocol.org
Version: 1
Chain ID: 56
Nonce: {nonce}
Issued At: {issued_at}
Resources:
- https://privy.io"""
        
        return message, issued_at
    
    def sign_message(self, private_key, message):
        """使用私钥对消息进行签名"""
        try:
            if not private_key.startswith('0x'):
                private_key = '0x' + private_key
                
            # 创建账户对象
            account = Account.from_key(private_key)
            
            # 对消息进行编码（以太坊标准格式）
            encoded_message = encode_defunct(text=message)
            
            # 生成签名
            signature = account.sign_message(encoded_message)
            
            return signature.signature.hex()
            
        except Exception as e:
            self.safe_log_message(f"签名生成失败: {str(e)}")
            return None
    
    def authenticate_wallet(self, wallet_address, message, signature):
        """发送认证请求（带重试机制）"""
        import random
        
        max_retries = 5
        base_delay = 3  # 基础延迟时间
        
        for attempt in range(max_retries):
            try:
                url = 'https://auth.privy.io/api/v1/siwe/authenticate'
                
                # 生成随机的privy-ca-id，避免被识别为同一客户端
                import uuid
                random_ca_id = str(uuid.uuid4())
                self.safe_log_message(f"认证请求时使用随机privy-ca-id: {random_ca_id[:8]}...")
                
                headers = {
                    'Content-Type': 'application/json',
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Origin': 'https://app.wardenprotocol.org',
                    'Referer': 'https://app.wardenprotocol.org/',
                    'Accept': 'application/json, text/plain, */*',
                    'Accept-Language': 'en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Cache-Control': 'no-cache',
                    'Pragma': 'no-cache',
                    'Sec-Fetch-Dest': 'empty',
                    'Sec-Fetch-Mode': 'cors',
                    'Sec-Fetch-Site': 'cross-site',
                    'privy-app-id': 'cm7f00k5c02tibel0m4o9tdy1',
                    'privy-ca-id': random_ca_id
                }
                
                payload = {
                    "message": message,
                    "signature": signature,
                    "chainId": "eip155:56",
                    "walletClientType": "okx_wallet",
                    "connectorType": "injected",
                    "mode": "login-or-sign-up"
                }
                
                proxies = self.get_proxies()
                
                response = requests.post(url, json=payload, headers=headers, proxies=proxies, timeout=30)
                
                if response.status_code == 200:
                    try:
                        response_data = response.json()
                        return response_data
                    except:
                        self.safe_log_message(f"认证响应不是JSON格式: {response.text}")
                        return None
                elif response.status_code == 429:
                    # 处理429错误，使用指数退避策略
                    if attempt < max_retries - 1:
                        # 计算延迟时间：基础延迟 * (2^尝试次数) + 随机时间
                        delay = base_delay * (2 ** attempt) + random.uniform(1, 3)
                        self.safe_log_message(f"认证请求遇到限流(429)，{delay:.1f}秒后重试 (尝试 {attempt + 1}/{max_retries})")
                        time.sleep(delay)
                        continue
                    else:
                        self.safe_log_message(f"认证请求失败，重试{max_retries}次后仍遇到限流，状态码: {response.status_code}, 响应: {response.text}")
                        return None
                else:
                    self.safe_log_message(f"认证请求失败，状态码: {response.status_code}, 响应: {response.text}")
                    return None
                    
            except Exception as e:
                if attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt) + random.uniform(1, 3)
                    self.safe_log_message(f"认证请求发生错误: {str(e)}，{delay:.1f}秒后重试 (尝试 {attempt + 1}/{max_retries})")
                    time.sleep(delay)
                    continue
                else:
                    self.safe_log_message(f"认证请求失败: {str(e)}")
                    return None
        
        return None
    
    def batch_wallet_auth(self, private_keys):
        """批量钱包认证"""
        successful_tokens = []
        
        try:
            self.safe_log_message("开始批量钱包认证流程...")
            
            for i, private_key in enumerate(private_keys):
                try:
                    self.safe_log_message(f"正在认证钱包 {i+1}/{len(private_keys)}...")
                    
                    # 1. 获取钱包地址
                    wallet_address = self.get_wallet_address(private_key)
                    if not wallet_address:
                        self.safe_log_message(f"钱包 {i+1} 获取地址失败，跳过")
                        continue
                    
                    self.safe_log_message(f"钱包 {i+1} 地址: {wallet_address}")
                    
                    # 2. 获取nonce
                    nonce = self.get_nonce(wallet_address)
                    if not nonce:
                        self.safe_log_message(f"钱包 {i+1} 获取nonce失败，跳过")
                        continue
                    
                    # 3. 创建SIWE消息
                    message, issued_at = self.create_siwe_message(wallet_address, nonce)
                    
                    # 4. 生成签名
                    signature = self.sign_message(private_key, message)
                    if not signature:
                        self.safe_log_message(f"钱包 {i+1} 签名生成失败，跳过")
                        continue
                    
                    # 5. 发送认证请求
                    auth_result = self.authenticate_wallet(wallet_address, message, signature)
                    if auth_result:
                        # 检查认证结果中是否包含token
                        token = None
                        if 'token' in auth_result:
                            token = auth_result['token']
                        elif 'accessToken' in auth_result:
                            token = auth_result['accessToken']
                        elif 'jwt' in auth_result:
                            token = auth_result['jwt']
                        
                        if token:
                            successful_tokens.append(token)
                            self.safe_log_message(f"钱包 {i+1} 认证成功，获取到token: {token[:50]}...")
                        else:
                            self.safe_log_message(f"钱包 {i+1} 认证成功但未找到token: {json.dumps(auth_result, ensure_ascii=False)}")
                    else:
                        self.safe_log_message(f"钱包 {i+1} 认证失败")
                    
                    # 延迟避免请求过快，使用随机化延迟
                    import random
                    delay = random.uniform(5, 8)  # 5-8秒的随机延迟
                    self.safe_log_message(f"等待 {delay:.1f} 秒后处理下一个钱包...")
                    time.sleep(delay)
                    
                except Exception as e:
                    self.safe_log_message(f"钱包 {i+1} 认证过程出错: {str(e)}")
            
            # 保存成功获取的token
            try:
                if successful_tokens:
                    self.save_tokens_to_file(successful_tokens)
                    self.safe_log_message(f"批量认证完成！成功获取 {len(successful_tokens)} 个token，已保存到tokens.txt")
                    
                    # 通过消息队列通知主线程重新加载token
                    self.message_queue.put({'type': 'reload_tokens'})
                else:
                    self.safe_log_message("批量认证完成，但未获取到任何有效token")
            except Exception as e:
                self.safe_log_message(f"批量认证完成后处理失败: {str(e)}")
                
        except Exception as e:
            # 捕获整个认证流程中的任何异常，防止GUI退出
            self.safe_log_message(f"批量钱包认证过程中发生严重错误: {str(e)}")
            import traceback
            traceback.print_exc()  # 打印详细的错误堆栈到控制台

    def save_tokens_to_file(self, new_tokens):
        """将新获取的token覆盖保存到tokens.txt文件"""
        try:
            # 直接覆盖写入文件（不读取现有token）
            with open('tokens.txt', 'w', encoding='utf-8') as f:
                for token in new_tokens:
                    f.write(token + '\n')
            
            self.safe_log_message(f"已覆盖保存 {len(new_tokens)} 个token到tokens.txt")
            
        except Exception as e:
            self.safe_log_message(f"保存token到文件失败: {str(e)}")

def main():
    root = tk.Tk()
    app = WardenGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main() 