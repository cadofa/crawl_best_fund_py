#! -*-coding: utf8-*-
import random
import time
import pickle
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
TEST_COUNT = 4 * 5 + 1

step_interval = [5,6,8,10,13,15,18,21,34,55,34,21,18,15,13,10]

touch_step = 6

B_profit_loss = {'B_profit_loss_position': 0, 'B_profit_loss_close': 0}
B_profit_loss_sum = []
S_profit_loss = {'S_profit_loss_position': 0, 'S_profit_loss_close': 0}
S_profit_loss_sum = []


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
    global B_operation_stack, B_Position_list, step_interval, B_profit_loss, touch_step
    global S_operation_stack, S_position_list, S_profit_loss
    market_data = create_index_data()
    B_Position_list = []
    B_operation_stack = []
    S_position_list = []
    S_operation_stack = []
    x_c = 0
    for i in market_data:
        print
        print "多单持仓详情", B_Position_list
        print "----------------------------最新行情---------------------------------------", i,"------------"*2 , x_c
        print
        x_c += 1
        #初始化建仓
        if not B_Position_list:
            B_Position_list.append(i + 1)
            print "多单初始化建仓"
            print "买入开仓", i+1
            print "多单持仓详情", B_Position_list
            B_operation_stack.append((x_c, i + 1, "B"))

        #初始化建仓
        if not S_position_list:
            S_position_list.append(i - 1)
            print "空单初始化建仓"
            print "卖出开仓", i+1
            print "空单持仓详情", S_position_list
            S_operation_stack.append((x_c, i - 1, "S"))

        #有过操作，没有持仓
        if B_operation_stack and not B_Position_list:
            #如果上一次是卖出，当前价格比上一次卖出价格低出步长，继续买
            if B_operation_stack[-1][2] == "S" and B_operation_stack[-1][1] - i >= touch_step:
                B_Position_list.append(i + 1)
                print "上一次操作是卖出，当前价格比上一次卖出价格低出摸顶步长，继续买"
                print "多单买入开仓", i+1
                print "多单持仓详情", B_Position_list
                B_operation_stack.append((x_c, i + 1, "B"))

        #有过操作，没有持仓
        if S_operation_stack and not S_position_list:
            #如果上一次是买入，当前价格比上一次买入价格高出步长，继续卖
            if S_operation_stack[-1][2] == "B" and i - S_operation_stack[-1][1] >= touch_step:
                S_position_list.append(i - 1)
                print "上一次操作是买入，当前价格比上一次买入价格高出摸底步长，继续卖"
                print "空单卖出开仓", i - 1
                print "空单持仓详情", S_position_list
                S_operation_stack.append((x_c, i - 1, "S"))
        
        B_last_index = B_Position_list.index(B_Position_list[-1])
        #根据买入步长逐步买进
        if (B_Position_list[-1] - i) >= step_interval[B_last_index]:
            B_Position_list.append(i + 1)
            print "当前点位比最后持仓点位低出指定间隔步长继续买入开仓"
            print "多单买入开仓", i+1
            print "多单持仓详情", B_Position_list
            B_operation_stack.append((x_c, i + 1, "B"))
        
        S_last_index = S_position_list.index(S_position_list[-1])
        #根据卖出步长逐步卖出
        if (i - S_position_list[-1]) >= step_interval[S_last_index]:
            S_position_list.append(i - 1)
            print "当前点位比最后持仓点位高出指定间隔步长继续卖出开仓"
            print "空单卖出开仓", i - 1
            print "空单持仓详情", S_position_list
            S_operation_stack.append((x_c, i - 1, "S"))

        #如果比上一次买入高指定步长，卖出
        if (i - B_Position_list[-1]) >= touch_step:
            B_operation_stack.append((x_c, i - 1, "S"))
            print "当前价格比上一次买入高摸顶步长，卖出平仓"
            print "卖出平仓", i - 1
            B_profit_loss_this_close = (i - 1)  - B_Position_list[-1]
            B_Position_list.remove(B_Position_list[-1])
            print "多单持仓详情", B_Position_list
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
            S_profit_loss["S_profit_loss_close"] = S_profit_loss["S_profit_loss_close"] + S_profit_loss_this_close
            print "空单平仓收益", S_profit_loss

        #time.sleep(1)
    print "多单持仓数据", B_Position_list, "收盘价", market_data[-1]
    save_close_price(market_data[-1])
    B_position_close_profit = sum([(market_data[-1] - i) for i in B_Position_list])
    print "多单收盘持仓结算盈亏", B_position_close_profit
    B_profit_loss["B_profit_loss_position"] = B_position_close_profit
    B_profit_loss["B_profit_loss"] = B_profit_loss["B_profit_loss_position"] + B_profit_loss['B_profit_loss_close']
    
    print "空单持仓数据", S_position_list, "收盘价", market_data[-1]
    S_position_close_profit = sum([(i - market_data[-1]) for i in S_position_list])
    print "空单收盘持仓结算盈亏", S_position_close_profit
    S_profit_loss["S_profit_loss_position"] = S_position_close_profit
    S_profit_loss["S_profit_loss"] = S_profit_loss["S_profit_loss_position"] + S_profit_loss['S_profit_loss_close']
    
    return market_data
        

for i in range(1, TEST_COUNT):
    image_name = "image/image%s.png" % i
    print "start", image_name
    fut_data = test_strategy()
    print "多单累计盈亏", B_profit_loss
    print "多单操作次数", len(B_operation_stack)
    print
    B_profit_loss_sum.append(B_profit_loss["B_profit_loss"])
    #time.sleep(2)
         
    ypoints = np.array(fut_data)
    plt.plot(ypoints)
    #print "操作记录", B_operation_stack
    for i in B_operation_stack:
        if B_operation_stack[-1][2] == "B":
            plt.annotate("B", [i[0], i[1]], color="red")
        if B_operation_stack[-1][2] == "S":
            plt.annotate("S", [i[0], i[1]], color="green")
    #plt.text(118, max(fut_data), str(B_profit_loss), fontsize=12)
    #plt.savefig(image_name)
    #plt.close()
    
    B_profit_loss = {'B_profit_loss_position': 0, 'B_profit_loss_close': 0}

    print "空单累计盈亏", S_profit_loss
    print "空单操作次数", len(S_operation_stack)
    print
    S_profit_loss_sum.append(S_profit_loss["S_profit_loss"])
    
    S_profit_loss = {'S_profit_loss_position': 0, 'S_profit_loss_close': 0}

print "多单历史盈亏列表", B_profit_loss_sum, len(B_profit_loss_sum)
total_B_profit_loss = 0
total_B_profit_loss_list = []
for i in B_profit_loss_sum:
    total_B_profit_loss += i
    total_B_profit_loss_list.append(total_B_profit_loss)
print "多单累计盈亏列表", total_B_profit_loss_list
print "多单最大亏损", min(B_profit_loss_sum)
print "多单最大盈利", max(B_profit_loss_sum)
print "多单亏损次数", len([i for i in B_profit_loss_sum if i < 0])
B_win_count =  len([i for i in B_profit_loss_sum if i > 0])
print "多单盈利次数", B_win_count
print "多单总体胜率", float(B_win_count)/len(B_profit_loss_sum)
print "多单多次累计盈亏总和", sum(B_profit_loss_sum)
print "\n\n"
print "空单历史盈亏列表", S_profit_loss_sum, len(S_profit_loss_sum)
total_S_profit_loss = 0
total_S_profit_loss_list = []
for i in S_profit_loss_sum:
    total_S_profit_loss += i
    total_S_profit_loss_list.append(total_S_profit_loss)
print "空单累计盈亏列表", total_S_profit_loss_list
print "空单最大亏损", min(S_profit_loss_sum)
print "空单最大盈利", max(S_profit_loss_sum)
print "空单亏损次数", len([i for i in S_profit_loss_sum if i < 0])
S_win_count =  len([i for i in S_profit_loss_sum if i > 0])
print "空单盈利次数", S_win_count
print "空单总体胜率", float(S_win_count)/len(S_profit_loss_sum)
print "空单多次累计盈亏总和", sum(S_profit_loss_sum)

total_profit = np.array(total_B_profit_loss_list)
#plt.plot(total_profit)
#plt.savefig("image/YieldCurve.png")
#plt.close()
