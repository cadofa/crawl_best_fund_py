# -*- coding: utf-8 -*-
import re
import smtplib
import requests
import json
import argparse
import numpy
import sys
from bs4 import BeautifulSoup

code_name_list = ['F003N_FUND33', 'F008', 'F009', 'F011', 'F015N_FUND33', 'F012']
weights_list =   [1,              0.9,    0.8,    0.7,    0.6,            0.5]
weights_l_tw =   [0.5,            0.6,    0.7,    0.8,    0.9,            1]
weights_l_th =   [1,              1,      1,      1,      1,              1]

def safe_convert(value):
    """安全转换值为浮点数，处理空值和无效数据"""
    if value is None or value == '':
        return float('-inf')
    if isinstance(value, str):
        clean_value = value.replace('%', '').replace(',', '').strip()
        if clean_value in ['', '--', 'N/A', 'null']:
            return float('-inf')
        try:
            return float(clean_value)
        except ValueError:
            return float('-inf')
    try:
        return float(value)
    except (TypeError, ValueError):
        return float('-inf')

def sort_dict(response_dict, key_to_sort):
    """安全排序函数，处理空值和无效数据"""
    # 过滤掉键值对中不包含 key_to_sort 的项
    filtered_dict = {
        k: v for k, v in response_dict.items() 
        if isinstance(v, dict) and key_to_sort in v
    }
    
    # 使用安全转换进行排序
    sorted_list = sorted(
        filtered_dict.items(),
        key=lambda item: safe_convert(item[1].get(key_to_sort)),
        reverse=True
    )
    
    rank = 1
    for s in sorted_list:
        value = s[1].get(key_to_sort)
        converted_value = safe_convert(value)
        if converted_value != float('-inf'):
            response_dict[s[0]][key_to_sort] = rank
            rank += 1
        else:
            # 保留原始值作为标记
            response_dict[s[0]][key_to_sort] = value

    return response_dict

def handle_fund_name(response_dict):
    for s, fund_data in list(response_dict.items()):
        if not isinstance(fund_data, dict):
            continue
            
        name_str = fund_data.get('name', '')
        if not isinstance(name_str, str):
            name_str = str(name_str)
            
        # 清理特殊字符和多余空格
        cleaned_name = re.sub(r'[^\w\u4e00-\u9fff]', ' ', name_str).strip()
        cleaned_name = re.sub(r'\s+', ' ', cleaned_name)
        
        # 如果名称完全无效，使用默认值
        if not cleaned_name:
            cleaned_name = "Unknown Fund"
        
        response_dict[s]['name'] = cleaned_name

    return response_dict

def crawl_data(url):
    global code_name_list

    print(f"正在获取数据: {url}")
    try:
        rs = requests.get(url, timeout=10)
        rs.raise_for_status()  # 检查HTTP错误
    except requests.RequestException as e:
        print(f"请求失败: {str(e)}")
        return {}
    
    response_str = rs.text
    
    # 1. 检查是否为 JSONP 格式
    if response_str.startswith('g(') and response_str.endswith(');'):
        # 移除 JSONP 包装：去掉开头的 'g(' 和结尾的 ');'
        json_str = response_str[2:-2]
    elif response_str.startswith('g(') and response_str.endswith(')'):
        # 处理不带分号的 JSONP 格式
        json_str = response_str[2:-1]
    else:
        # 2. 尝试直接解析为标准 JSON
        json_str = response_str
        print("警告: 返回数据格式不符合JSONP格式，尝试直接解析为标准JSON")
    
    # 3. 替换 null 为 Python 的 None
    json_str = json_str.replace('null', 'None').replace('"null"', 'None')
    
    # 4. 安全解析数据
    try:
        response_data = eval(json_str)
    except SyntaxError as e:
        print(f"JSON解析错误: {e}")
        print(f"原始响应数据: {response_str[:500]}")
        return {}
    
    # 5. 提取核心数据
    try:
        response_dict = response_data['data']['data']
    except KeyError:
        print(f"数据结构错误，未找到 'data.data' 键")
        print(f"完整响应结构: {list(response_data.keys())}")
        return {}
    
    # 6. 改进数值处理
    for k, v in list(response_dict.items()):
        if not isinstance(v, dict):
            continue
            
        for key, value in v.items():
            if key == "code" or key == "name":
                continue
                
            # 尝试转换为数值
            if value is None or value in ['', '--', 'N/A', 'null']:
                v[key] = None
            elif isinstance(value, str):
                # 移除百分比符号和逗号
                clean_value = value.replace('%', '').replace(',', '').strip()
                try:
                    v[key] = float(clean_value)
                except ValueError:
                    v[key] = None
            else:
                try:
                    v[key] = float(value)
                except (TypeError, ValueError):
                    v[key] = None

    response_dict = handle_fund_name(response_dict)
    
    for k in code_name_list:
        response_dict = sort_dict(response_dict, k)

    return response_dict

def Computing_rankings(response_dict, weights_list):
    global code_name_list
    fund_data = []
    
    for k, v in list(response_dict.items()):
        if not isinstance(v, dict):
            continue
            
        ranking_list = []
        for c in code_name_list:
            value = v.get(c)
            if value is None:
                # 如果数据缺失，使用最大排名（最差）
                ranking_list.append(1000000)
            else:
                try:
                    ranking_list.append(int(value))
                except (TypeError, ValueError):
                    ranking_list.append(1000000)
        
        if not ranking_list:
            continue
            
        # 应用权重
        weighted_ranks = [r * w for r, w in zip(ranking_list, weights_list)]
        average = int(round(numpy.mean(weighted_ranks)))
        variance = int(round(numpy.var(ranking_list)))  # 使用原始排名计算方差
        
        fund_data.append([v.get('code', '') + "  " + v.get('name', 'Unnamed Fund'), average, variance])

    return fund_data

def create_mail_content(fund_data, type_name):
    if not fund_data:
        return "没有找到符合条件的基金数据"
    
    # 按平均排名排序
    fund_data.sort(key=lambda x: x[1])
    
    # 选取排名靠前的基金
    top_funds = fund_data[:index_number]
    
    content_lines = []
    for fund in top_funds:
        # 格式: 基金代码 基金名称 平均排名 方差
        content_lines.append(f"{fund[0]} {fund[1]} {fund[2]}")
    
    return '\n'.join(content_lines)

def get_code_name(mail_content):
    if not mail_content:
        return [], {}
    
    fund_code_name = []
    fund_code_name_dict = {}
    
    lines = mail_content.split("\n")
    for line in lines:
        parts = line.split()
        if len(parts) < 3:
            continue
            
        # 前两部分是代码和名称
        code_name = " ".join(parts[0:2])
        # 排名和方差在最后两个字段
        try:
            rank = parts[-2]
            variance = parts[-1]
        except IndexError:
            continue
        
        fund_code_name.append(code_name)
        fund_code_name_dict[code_name] = [rank, variance]
    
    return fund_code_name, fund_code_name_dict

def create_best_fund(code_name_one, code_name_two, code_name_three,
                    code_name_one_dict, code_name_two_dict, code_name_three_dict):
    # 找到所有三个列表都存在的基金
    common_funds = set(code_name_one) & set(code_name_two) & set(code_name_three)
    
    if not common_funds:
        print("没有找到在所有排名中都表现良好的基金")
        return
        
    best_fund_list = []
    for fund in common_funds:
        try:
            # 计算平均排名
            rank_avg = numpy.mean([
                float(code_name_one_dict[fund][0]),
                float(code_name_two_dict[fund][0]),
                float(code_name_three_dict[fund][0])
            ])
            
            # 计算平均方差
            var_avg = numpy.mean([
                float(code_name_one_dict[fund][1]),
                float(code_name_two_dict[fund][1]),
                float(code_name_three_dict[fund][1])
            ])
            
            best_fund_list.append([fund, rank_avg, var_avg])
        except (KeyError, ValueError):
            continue
    
    if not best_fund_list:
        print("数据不完整，无法计算最佳基金")
        return
        
    # 按方差排序（方差小表示稳定性高）
    best_fund_list.sort(key=lambda x: x[2])
    
    print("\n最佳基金（按稳定性排序）：")
    print("基金代码和名称             平均排名  平均方差")
    for fund in best_fund_list:
        print(f"{fund[0]:<30} {fund[1]:<8.1f} {fund[2]:<8.1f}")

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("type",
                        choices=['mixed', 'stock', 'bond', 'guaranteed'],
                        help="基金类型: mixed(混合型), stock(股票型), bond(债券型), guaranteed(保本型)")
    parser.add_argument("--index", type=int,
                        default=40, help="显示排名靠前的基金数量")
    args = parser.parse_args()
    
    global index_number
    index_number = args.index
    type_ = args.type
    
    # 基金类型映射
    fund_types = {
        'mixed': ('混合型', 'hhx'),
        'stock': ('股票型', 'gpx'),
        'bond': ('债券型', 'zqx'),
        'guaranteed': ('保本型', 'bbx')
    }
    
    if type_ not in fund_types:
        print(f"错误: 不支持的类型 {type_}")
        sys.exit(1)
        
    type_name, type_code = fund_types[type_]
    
    # 构建URL
    url = (f'http://fund.ijijin.cn/data/Net/info/'
           f'{type_code}_F008_desc_0_0_1_9999_0_0_0_jsonp_g.html')
    
    print(f"获取 {type_name} 基金数据...")
    response_dict = crawl_data(url)
    
    if not response_dict:
        print(f"错误: 无法获取 {type_name} 基金数据")
        sys.exit(1)
    
    print(f"\n使用权重1: {weights_list}")
    fund_data = Computing_rankings(response_dict, weights_list)
    mail_content = create_mail_content(fund_data, type_name)
    print(f"\n{type_name}基金排名 (权重1):")
    print(mail_content)
    code_name_one, code_name_one_dict = get_code_name(mail_content)
    
    print(f"\n使用权重2: {weights_l_tw}")
    fund_data = Computing_rankings(response_dict, weights_l_tw)
    mail_content = create_mail_content(fund_data, type_name)
    print(f"\n{type_name}基金排名 (权重2):")
    print(mail_content)
    code_name_two, code_name_two_dict = get_code_name(mail_content)
    
    print(f"\n使用权重3: {weights_l_th}")
    fund_data = Computing_rankings(response_dict, weights_l_th)
    mail_content = create_mail_content(fund_data, type_name)
    print(f"\n{type_name}基金排名 (权重3):")
    print(mail_content)
    code_name_three, code_name_three_dict = get_code_name(mail_content)
    
    print("\n综合分析最佳基金:")
    create_best_fund(code_name_one, code_name_two, code_name_three,
                     code_name_one_dict, code_name_two_dict, code_name_three_dict)