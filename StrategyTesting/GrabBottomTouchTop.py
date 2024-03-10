#! -*-coding: utf8-*-
import random
import time
import matplotlib as mpl
mpl.use('Agg')
import numpy as np
import matplotlib.pyplot as plt

START = 2500
SAMPLE_SIZE = 10000
TEST_COUNT = 50
copy_bottom_step = [3,5,8,13,21,34,55,89,144,233]
touch_top_step = 5
position_list = []
operation_stack = []
profit_loss = {'profit_loss_position': 0, 'profit_loss_close': 0}
profit_loss_sum = []


def generate_random_number(m_data, step, swing):
    choice_list = [0, step, (0 - step)]
    if m_data < START * (1 - swing):
        return m_data + 1
    if m_data > START * (1 + swing):
        return m_data - 1
    return m_data + random.choice(choice_list)

def create_index_data():
    swing = random.choice([0.005, 0.01, 0.015, 0.02, 0.025, 0.03, 0.035, 0.04, 0.045, 0.05])
    random_number_list = []
    global START
    m_data = START
    print "start", m_data
    print "swing", swing
    for i in range(SAMPLE_SIZE):
        m_data = generate_random_number(m_data, 1, swing)
        random_number_list.append(m_data)

    step_list = []
    for i in range(1, len(random_number_list)):
        step_list.append(random_number_list[i] - random_number_list[i - 1])

    index_list = []
    for i in range(len(step_list)):
        index_list.append((random_number_list[i], step_list[i]))
    print "max", max(random_number_list)
    print "min", min(random_number_list)
    return random_number_list

def test_strategy():
    global operation_stack, position_list, copy_bottom_step, profit_loss, touch_top_step
    market_data = create_index_data()
    x_c = -1
    for i in market_data:
        x_c += 1
        #print
        #print "------------------最新行情---------------------", i, "x坐标值", x_c
        #print
        #没有持仓买入
        if not len(position_list):
            position_list.append(i)
            operation_stack.append((x_c, i, "B"))
            
        last_index = position_list.index(position_list[-1])
        #根据买入步长逐步买进
        if (position_list[-1] - i) >= copy_bottom_step[last_index]:
            position_list.append(i)
            operation_stack.append((x_c, i, "B"))
        
        #如果比上一次买入高指定步长，卖出
        if operation_stack[-1][2] == "B" and (i - position_list[-1]) >= touch_top_step:
            operation_stack.append((x_c, i, "S"))
            profit_loss_this_close = i - position_list[-1]
            position_list.remove(position_list[-1])
            profit_loss["profit_loss_close"] = profit_loss["profit_loss_close"] + profit_loss_this_close

            if not len(position_list):
                position_list.append(i)
                operation_stack.append((x_c, i, "B"))
        #如果上一次是卖出，当前价格比上一次卖出价格高出步长，继续卖
        if operation_stack[-1][2] == "S" and i - operation_stack[-1][1] >= touch_top_step and len(position_list) > 0:
            operation_stack.append((x_c, i, "S"))
            profit_loss_this_close = i - position_list[-1]
            position_list.remove(position_list[-1])
            profit_loss["profit_loss_close"] = profit_loss["profit_loss_close"] + profit_loss_this_close

            if not len(position_list):
                position_list.append(i)
                operation_stack.append((x_c, i, "B"))

        #print "操作记录", operation_stack
        #print "累计盈亏", profit_loss
        #time.sleep(2)

    print "持仓数据", position_list, "收盘数据", market_data[-1]
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
    """
    plt.plot(ypoints)
    for i in range(30):
        x_p = random.randint(0,SAMPLE_SIZE-1)
        plt.annotate("B", [x_p, fut_data[x_p]], color="red")
    for i in range(30):
        x_p = random.randint(0,SAMPLE_SIZE-1)
        plt.annotate("S", [x_p, fut_data[x_p]], color="green")
    plt.text(2580, 2500, "Profit and loss -1000", fontsize=16)
    plt.savefig(image_name)
    plt.close()
    """
    position_list = []
    operation_stack = []
    profit_loss = {'profit_loss_position': 0, 'profit_loss_close': 0}

print "多次累计盈亏列表", profit_loss_sum
print "多次累计盈亏总和", sum(profit_loss_sum)