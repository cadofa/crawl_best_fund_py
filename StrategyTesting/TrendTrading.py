#! -*-coding: utf8-*-
import random
import time
import pickle
import matplotlib as mpl
mpl.use('Agg')
import numpy as np
import matplotlib.pyplot as plt
from utils import generate_random_number, create_index_data, get_close_price


def save_close_price(close):
    with open('close.pk', 'wb') as file:
        pickle.dump(close, file)

TEST_COUNT = 2

tick_data_list = []
dev_value_list = []

def onTick(tick):
    global tick_data_list, dev_value_list
    #print
    #print "行情数据-------------------*----------------------",  tick
    tick_data_list.append(tick)
    #print tick_data_list
    tick_mean = np.mean(tick_data_list)
    dev_value_list.append((tick - tick_mean)/tick_mean*100)           
    #time.sleep(1)

def test_strategy():
    market_data = create_index_data()
    for i in market_data:
        onTick(i)

    print "均值", np.mean(tick_data_list)
    print "最大最小偏离", max(dev_value_list), min(dev_value_list)
        

for i in range(1, TEST_COUNT):
    fut_data = test_strategy()
    #time.sleep(2)
         
#    ypoints = np.array(fut_data)
#    plt.plot(ypoints)
#    #print "操作记录", operation_stack
#    for i in operation_stack:
#        if operation_stack[-1][2] == "B":
#            plt.annotate("B", [i[0], i[1]], color="red")
#        if operation_stack[-1][2] == "S":
#            plt.annotate("S", [i[0], i[1]], color="green")
#    plt.text(118, max(fut_data), str(profit_loss), fontsize=12)
#    plt.savefig(image_name)
#    plt.close()
#    
#    operation_stack = []
#    profit_loss = {'profit_loss_position': 0, 'profit_loss_close': 0}

#print "历史盈亏列表", profit_loss_sum, len(profit_loss_sum)
#total_profit_loss = 0
#total_profit_loss_list = []
#for i in profit_loss_sum:
#    total_profit_loss += i
#    total_profit_loss_list.append(total_profit_loss)
#print "累计盈亏列表", total_profit_loss_list
#print "最大亏损", min(profit_loss_sum)
#print "最大盈利", max(profit_loss_sum)
#print "亏损次数", len([i for i in profit_loss_sum if i < 0])
#win_count =  len([i for i in profit_loss_sum if i > 0])
#print "盈利次数", win_count
#print "总体胜率", float(win_count)/len(profit_loss_sum)
#print "多次累计盈亏总和", sum(profit_loss_sum)
#
#total_profit = np.array(total_profit_loss_list)
#plt.plot(total_profit)
#plt.savefig("image/YieldCurve.png")
#plt.close()
