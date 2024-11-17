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
TEST_COUNT = 4 * 5 * 4 + 1

copy_top_step = [5,6,8,10,13,15,18,21,34,55,34,21,18,15,13,10]

touch_bottom_step = 6

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
    global S_operation_stack, S_position_list, copy_top_step, S_profit_loss, touch_bottom_step
    market_data = create_index_data()
    S_position_list = []
    S_operation_stack = []
    x_c = 0
    for i in market_data:
        print
        print "持仓详情", S_position_list
        print "----------------------------最新行情---------------------------------------", i,"------------"*2 , x_c
        print
        x_c += 1
        #初始化建仓
        if not S_position_list:
            S_position_list.append(i - 1)
            print "初始化建仓"
            print "卖出开仓", i+1
            print "持仓详情", S_position_list
            S_operation_stack.append((x_c, i - 1, "S"))
            continue

        #有过操作，没有持仓
        if S_operation_stack and not S_position_list:
            #如果上一次是买入，当前价格比上一次买入价格高出步长，继续卖
            if S_operation_stack[-1][2] == "B" and i - S_operation_stack[-1][1] >= touch_bottom_step:
                S_position_list.append(i - 1)
                print "上一次操作是买入，当前价格比上一次买入价格高出摸底步长，继续卖"
                print "卖出开仓", i - 1
                print "持仓详情", S_position_list
                S_operation_stack.append((x_c, i - 1, "S"))
                continue

            continue
        
        last_index = S_position_list.index(S_position_list[-1])
        #根据卖出步长逐步卖出
        if (i - S_position_list[-1]) >= copy_top_step[last_index]:
            S_position_list.append(i - 1)
            print "当前点位比最后持仓点位高出指定间隔步长继续卖出开仓"
            print "卖出开仓", i - 1
            print "持仓详情", S_position_list
            S_operation_stack.append((x_c, i - 1, "S"))
            continue
        
        #如果比上一次卖出低指定步长，买入
        if (S_position_list[-1] - i) >= touch_bottom_step:
            S_operation_stack.append((x_c, i + 1, "B"))
            print "当前价格比上一次卖出低摸底步长，买入平仓"
            print "买入平仓", i + 1
            S_profit_loss_this_close = S_position_list[-1] - (i + 1)
            S_position_list.remove(S_position_list[-1])
            print "持仓详情", S_position_list
            S_profit_loss["S_profit_loss_close"] = S_profit_loss["S_profit_loss_close"] + S_profit_loss_this_close
            print "平仓收益", S_profit_loss

            continue

        #如果上一次是买入，当前价格比上一次买入价格低出步长，继续买
        if S_operation_stack[-1][2] == "B" and S_operation_stack[-1][1] - i >= touch_bottom_step and len(S_position_list) > 0:
            S_operation_stack.append((x_c, i + 1, "B"))
            print "上一次是买入，当前价格比上一次买入价格低出摸底步长，继续买入平仓"
            print "买入平仓", i + 1
            S_profit_loss_this_close = S_position_list[-1] - (i + 1)
            S_position_list.remove(S_position_list[-1])
            print "持仓详情", S_position_list
            S_profit_loss["S_profit_loss_close"] = S_profit_loss["S_profit_loss_close"] + S_profit_loss_this_close
            print "平仓收益", S_profit_loss

            continue

        #time.sleep(1)
    print "持仓数据", S_position_list, "收盘价", market_data[-1]
    save_close_price(market_data[-1])
    position_close_profit = sum([(i - market_data[-1]) for i in S_position_list])
    print "收盘持仓结算盈亏", position_close_profit
    S_profit_loss["S_profit_loss_position"] = position_close_profit
    S_profit_loss["S_profit_loss"] = S_profit_loss["S_profit_loss_position"] + S_profit_loss['S_profit_loss_close']
    return market_data
        

for i in range(1, TEST_COUNT):
    image_name = "image/image%s.png" % i
    print "start", image_name
    fut_data = test_strategy()
    print "累计盈亏", S_profit_loss
    print "操作次数", len(S_operation_stack)
    print
    S_profit_loss_sum.append(S_profit_loss["S_profit_loss"])
    #time.sleep(2)
         
    ypoints = np.array(fut_data)
    plt.plot(ypoints)
    #print "操作记录", S_operation_stack
    for i in S_operation_stack:
        if S_operation_stack[-1][2] == "B":
            plt.annotate("B", [i[0], i[1]], color="red")
        if S_operation_stack[-1][2] == "S":
            plt.annotate("S", [i[0], i[1]], color="green")
    #plt.text(118, max(fut_data), str(S_profit_loss), fontsize=12)
    #plt.savefig(image_name)
    #plt.close()
    
    S_position_list = []
    S_operation_stack = []
    S_profit_loss = {'S_profit_loss_position': 0, 'S_profit_loss_close': 0}

print "历史盈亏列表", S_profit_loss_sum, len(S_profit_loss_sum)
total_S_profit_loss = 0
total_S_profit_loss_list = []
for i in S_profit_loss_sum:
    total_S_profit_loss += i
    total_S_profit_loss_list.append(total_S_profit_loss)
print "累计盈亏列表", total_S_profit_loss_list
print "最大亏损", min(S_profit_loss_sum)
print "最大盈利", max(S_profit_loss_sum)
print "亏损次数", len([i for i in S_profit_loss_sum if i < 0])
win_count =  len([i for i in S_profit_loss_sum if i > 0])
print "盈利次数", win_count
print "总体胜率", float(win_count)/len(S_profit_loss_sum)
print "多次累计盈亏总和", sum(S_profit_loss_sum)

total_profit = np.array(total_S_profit_loss_list)
#plt.plot(total_profit)
#plt.savefig("image/YieldCurve.png")
#plt.close()
