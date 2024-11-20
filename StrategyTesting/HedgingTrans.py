#! -*-coding: utf8-*-
import random
import time
import pickle
import json
import matplotlib as mpl
mpl.use('Agg')
import numpy as np
import matplotlib.pyplot as plt

def get_close_price():
    try:
        with open('close.pk', 'rb') as file:
            close = pickle.load(file)
        return close
    except IOError, e:
        return 2500

def save_close_price(close):
    with open('close.pk', 'wb') as file:
        pickle.dump(close, file)

SAMPLE_SIZE = 3600
TEST_COUNT = 5

B_S_DIFF = 0

step_interval = [5,6,8,10,13,15,18,21,34,55,34,21,18,15,13,10]

touch_step = 6

B_profit_close_list = []
S_profit_close_list = []

def read_B_operation():
    try:
        with open('B_operation_stack.json', 'r') as file:
            return json.load(file)
    except Exception, e:
        return []

def read_S_operation():
    try:
        with open('S_operation_stack.json', 'r') as file:
            return json.load(file)
    except Exception, e:
        return []

def generate_random_number(start, m_data, step, swing):
    #choice_list = [0, step, (0 - step), step * 2, (0 - step)*2]
    choice_list = [0, step, (0 - step)]
    if m_data < start * (1 - swing):
        return m_data + 1
    if m_data > start * (1 + swing):
        return m_data - 1
    if m_data < 2000:
        return m_data + 1
    if m_data > 3500:
        return m_data - 1
    return m_data + random.choice(choice_list)

def create_index_data():
    swing = random.choice([0.003, 0.005, 0.006, 0.008, 0.01, 0.013, 0.015, 0.018, 0.021, 0.034])
    random_number_list = []
    start = get_close_price() + random.choice([0, -3,-5,-8,-13,3,5,8,13])
    m_data = start
    print "开盘价", m_data
    print "日内振幅", swing
    for i in range(SAMPLE_SIZE):
        m_data = generate_random_number(start, m_data, 1, swing)
        random_number_list.append(m_data)


    print "最高价", max(random_number_list)
    print "最低价", min(random_number_list)
    return random_number_list

def test_strategy():
    global B_operation_stack, B_profit_close_list, step_interval, touch_step
    global S_operation_stack, S_profit_close_list
    market_data = create_index_data()
    B_profit_loss = {'B_profit_loss_close': 0}
    S_profit_loss = {'S_profit_loss_close': 0}
    B_Position_list = []
    B_operation_stack = []
    S_position_list = []
    S_operation_stack = []
    x_c = 0
    for i in market_data:
        print
        print "多单持仓详情", B_Position_list
        print "空单持仓详情", S_position_list
        print "----------------------------最新行情---------------------------------------", i,"------------"*2 , x_c
        print
        x_c += 1
        #初始化建仓
        if not B_Position_list and (len(B_Position_list) - len(S_position_list) <= B_S_DIFF):
            B_Position_list.append(i + 1)
            print "多单初始化建仓"
            print "买入开仓", i+1
            print "多单持仓详情", B_Position_list
            print "空单持仓详情", S_position_list
            B_operation_stack.append((x_c, i + 1, "B"))

        #初始化建仓
        if not S_position_list and (len(S_position_list) - len(B_Position_list) <= B_S_DIFF):
            S_position_list.append(i - 1)
            print "空单初始化建仓"
            print "卖出开仓", i+1
            print "空单持仓详情", S_position_list
            print "多单持仓详情", B_Position_list
            S_operation_stack.append((x_c, i - 1, "S"))

        #有过操作，没有持仓
        if B_operation_stack and not B_Position_list and (len(B_Position_list) - len(S_position_list) <= B_S_DIFF):
            #如果上一次是卖出，当前价格比上一次卖出价格低出步长，继续买
            if B_operation_stack[-1][2] == "S" and B_operation_stack[-1][1] - i >= touch_step:
                B_Position_list.append(i + 1)
                print "上一次操作是卖出，当前价格比上一次卖出价格低出摸顶步长，继续买"
                print "多单买入开仓", i+1
                print "多单持仓详情", B_Position_list
                print "空单持仓详情", S_position_list
                B_operation_stack.append((x_c, i + 1, "B"))

        #有过操作，没有持仓
        if S_operation_stack and not S_position_list and (len(S_position_list) - len(B_Position_list) <= B_S_DIFF):
            #如果上一次是买入，当前价格比上一次买入价格高出步长，继续卖
            if S_operation_stack[-1][2] == "B" and i - S_operation_stack[-1][1] >= touch_step:
                S_position_list.append(i - 1)
                print "上一次操作是买入，当前价格比上一次买入价格高出摸底步长，继续卖"
                print "空单卖出开仓", i - 1
                print "空单持仓详情", S_position_list
                print "多单持仓详情", B_Position_list
                S_operation_stack.append((x_c, i - 1, "S"))
        
        B_last_index = B_Position_list.index(B_Position_list[-1])
        #根据买入步长逐步买进
        if (B_Position_list[-1] - i) >= step_interval[B_last_index] and (len(B_Position_list) - len(S_position_list) <= B_S_DIFF):
            B_Position_list.append(i + 1)
            print "当前点位比最后持仓点位低出指定间隔步长继续买入开仓"
            print "多单买入开仓", i+1
            print "多单持仓详情", B_Position_list
            print "空单持仓详情", S_position_list
            B_operation_stack.append((x_c, i + 1, "B"))
        
        S_last_index = S_position_list.index(S_position_list[-1])
        #根据卖出步长逐步卖出
        if (i - S_position_list[-1]) >= step_interval[S_last_index] and (len(S_position_list) - len(B_Position_list) <= B_S_DIFF):
            S_position_list.append(i - 1)
            print "当前点位比最后持仓点位高出指定间隔步长继续卖出开仓"
            print "空单卖出开仓", i - 1
            print "空单持仓详情", S_position_list
            print "多单持仓详情", B_Position_list
            S_operation_stack.append((x_c, i - 1, "S"))

        #如果比上一次买入高指定步长，卖出
        if (i - B_Position_list[-1]) >= touch_step:
            B_operation_stack.append((x_c, i - 1, "S"))
            print "当前价格比上一次买入高摸顶步长，卖出平仓"
            print "卖出平仓", i - 1
            B_profit_loss_this_close = (i - 1)  - B_Position_list[-1]
            B_Position_list.remove(B_Position_list[-1])
            print "多单持仓详情", B_Position_list
            print "空单持仓详情", S_position_list
            B_profit_loss["B_profit_loss_close"] = B_profit_loss["B_profit_loss_close"] + B_profit_loss_this_close
            print "多单平仓收益", B_profit_loss

        #如果比上一次卖出低指定步长，买入
        if (S_position_list[-1] - i) >= touch_step:
            S_operation_stack.append((x_c, i + 1, "B"))
            print "当前价格比上一次卖出低摸底步长，买入平仓"
            print "买入平仓", i + 1
            S_profit_loss_this_close = S_position_list[-1] - (i + 1)
            S_position_list.remove(S_position_list[-1])
            print "空单持仓详情", S_position_list
            print "多单持仓详情", B_Position_list
            S_profit_loss["S_profit_loss_close"] = S_profit_loss["S_profit_loss_close"] + S_profit_loss_this_close
            print "空单平仓收益", S_profit_loss

        #如果上一次是卖出，当前价格比上一次卖出价格高出步长，继续卖
        if B_operation_stack[-1][2] == "S" and i - B_operation_stack[-1][1] >= touch_step and len(B_Position_list) > 0:
            B_operation_stack.append((x_c, i - 1, "S"))
            print "上一次是卖出，当前价格比上一次卖出价格高出摸顶步长，继续卖出平仓"
            print "卖出平仓", i - 1
            B_profit_loss_this_close = i - 1 - B_Position_list[-1]
            B_Position_list.remove(B_Position_list[-1])
            print "多单持仓详情", B_Position_list
            print "空单持仓详情", S_position_list
            B_profit_loss["B_profit_loss_close"] = B_profit_loss["B_profit_loss_close"] + B_profit_loss_this_close
            print "多单平仓收益", B_profit_loss

        #如果上一次是买入，当前价格比上一次买入价格低出步长，继续买
        if S_operation_stack[-1][2] == "B" and S_operation_stack[-1][1] - i >= touch_step and len(S_position_list) > 0:
            S_operation_stack.append((x_c, i + 1, "B"))
            print "上一次是买入，当前价格比上一次买入价格低出摸底步长，继续买入平仓"
            print "空单买入平仓", i + 1
            S_profit_loss_this_close = S_position_list[-1] - (i + 1)
            S_position_list.remove(S_position_list[-1])
            print "空单持仓详情", S_position_list
            print "多单持仓详情", B_Position_list
            S_profit_loss["S_profit_loss_close"] = S_profit_loss["S_profit_loss_close"] + S_profit_loss_this_close
            print "空单平仓收益", S_profit_loss

        #time.sleep(1)
    save_close_price(market_data[-1])
    print "多单平仓收益", B_profit_loss
    B_profit_close_list.append(B_profit_loss["B_profit_loss_close"])   
    print "空单平仓收益", S_profit_loss
    S_profit_close_list.append(S_profit_loss["S_profit_loss_close"])
    
    return market_data
        

for i in range(1, TEST_COUNT):
    fut_data = test_strategy()
    print "多单平仓盈亏列表", B_profit_close_list
    print "多单平仓累计盈亏", sum(B_profit_close_list)
    print
         
    

    print "空单平仓盈亏列表", S_profit_close_list
    print "空单平仓累计盈亏", sum(S_profit_close_list)
    print

