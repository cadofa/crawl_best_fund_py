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

copy_bottom_step = [5,6,8,10,13,15,18,21,34,55,34,21,18,15,13,10]

touch_top_step = 5

profit_loss = {'profit_loss_position': 0, 'profit_loss_close': 0}
profit_loss_sum = []


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

    step_list = []
    for i in range(1, len(random_number_list)):
        step_list.append(random_number_list[i] - random_number_list[i - 1])

    index_list = []
    for i in range(len(step_list)):
        index_list.append((random_number_list[i], step_list[i]))
    print "最高价", max(random_number_list)
    print "最低价", min(random_number_list)
    return random_number_list

def test_strategy():
    global operation_stack, position_list, copy_bottom_step, profit_loss, touch_top_step
    market_data = create_index_data()
    position_list = []
    operation_stack = []
    x_c = 0
    for i in market_data:
        print
        print "持仓详情", position_list
        print "----------------------------最新行情---------------------------------------", i,"------------"*2 , x_c
        print
        x_c += 1
        #初始化建仓
        if not position_list and not operation_stack:
            position_list.append(i + 1)
            print "初始化建仓"
            print "买入开仓", i+1
            print "持仓详情", position_list
            operation_stack.append((x_c, i + 1, "B"))
            continue

        #有过操作，没有持仓
        if operation_stack and not position_list:
            #如果上一次是卖出，当前价格比上一次卖出价格低出步长，继续买
            if operation_stack[-1][2] == "S" and operation_stack[-1][1] - i >= touch_top_step:
                position_list.append(i + 1)
                print "上一次操作是卖出，当前价格比上一次卖出价格低出摸顶步长，继续买"
                print "买入开仓", i+1
                print "持仓详情", position_list
                operation_stack.append((x_c, i + 1, "B"))
                continue

            continue
        
        last_index = position_list.index(position_list[-1])
        #根据买入步长逐步买进
        if (position_list[-1] - i) >= copy_bottom_step[last_index]:
            position_list.append(i + 1)
            print "当前点位比最后持仓点位低出指定间隔步长继续买入开仓"
            print "买入开仓", i+1
            print "持仓详情", position_list
            operation_stack.append((x_c, i + 1, "B"))
            continue
        
        #如果比上一次买入高指定步长，卖出
        if (i - position_list[-1]) >= touch_top_step:
            operation_stack.append((x_c, i - 1, "S"))
            print "当前价格比上一次买入高摸顶步长，卖出平仓"
            print "卖出平仓", i - 1
            profit_loss_this_close = (i - 1)  - position_list[-1]
            position_list.remove(position_list[-1])
            print "持仓详情", position_list
            profit_loss["profit_loss_close"] = profit_loss["profit_loss_close"] + profit_loss_this_close
            print "平仓收益", profit_loss

            continue

        #如果上一次是卖出，当前价格比上一次卖出价格高出步长，继续卖
        if operation_stack[-1][2] == "S" and i - operation_stack[-1][1] >= touch_top_step and len(position_list) > 0:
            operation_stack.append((x_c, i - 1, "S"))
            print "上一次是卖出，当前价格比上一次卖出价格高出摸顶步长，继续卖出平仓"
            print "卖出平仓", i - 1
            profit_loss_this_close = i - 1 - position_list[-1]
            position_list.remove(position_list[-1])
            print "持仓详情", position_list
            profit_loss["profit_loss_close"] = profit_loss["profit_loss_close"] + profit_loss_this_close
            print "平仓收益", profit_loss

            continue

        #time.sleep(1)
    print "持仓数据", position_list, "收盘价", market_data[-1]
    save_close_price(market_data[-1])
    position_close_profit = sum([(market_data[-1] - i) for i in position_list])
    print "收盘持仓结算盈亏", position_close_profit
    profit_loss["profit_loss_position"] = position_close_profit
    profit_loss["profit_loss"] = profit_loss["profit_loss_position"] + profit_loss['profit_loss_close']
    return market_data
        

for i in range(1, TEST_COUNT):
    image_name = "image/image%s.png" % i
    print "start", image_name
    fut_data = test_strategy()
    print "累计盈亏", profit_loss
    print "操作次数", len(operation_stack)
    print
    profit_loss_sum.append(profit_loss["profit_loss"])
    #time.sleep(2)
         
    ypoints = np.array(fut_data)
    plt.plot(ypoints)
    #print "操作记录", operation_stack
    for i in operation_stack:
        if operation_stack[-1][2] == "B":
            plt.annotate("B", [i[0], i[1]], color="red")
        if operation_stack[-1][2] == "S":
            plt.annotate("S", [i[0], i[1]], color="green")
    #plt.text(118, max(fut_data), str(profit_loss), fontsize=12)
    #plt.savefig(image_name)
    #plt.close()
    
    position_list = []
    operation_stack = []
    profit_loss = {'profit_loss_position': 0, 'profit_loss_close': 0}

print "历史盈亏列表", profit_loss_sum, len(profit_loss_sum)
total_profit_loss = 0
total_profit_loss_list = []
for i in profit_loss_sum:
    total_profit_loss += i
    total_profit_loss_list.append(total_profit_loss)
print "累计盈亏列表", total_profit_loss_list
print "最大亏损", min(profit_loss_sum)
print "最大盈利", max(profit_loss_sum)
print "亏损次数", len([i for i in profit_loss_sum if i < 0])
win_count =  len([i for i in profit_loss_sum if i > 0])
print "盈利次数", win_count
print "总体胜率", float(win_count)/len(profit_loss_sum)
print "多次累计盈亏总和", sum(profit_loss_sum)

total_profit = np.array(total_profit_loss_list)
#plt.plot(total_profit)
#plt.savefig("image/YieldCurve.png")
#plt.close()
