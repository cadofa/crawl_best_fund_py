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

TEST_COUNT = 1001
position_list = {}
stop_loss_value = 3
stop_profit_value = 8
profit_and_loss = 0
operation_num = 0

def onTick(tick):
    global position_list, stop_loss_value, stop_profit_value, profit_and_loss, operation_num
    #print 
    #print "行情数据-------------------*----------------------",  tick
    #print "持仓数据", position_list
    #print "平仓盈亏", profit_and_loss
    #没有持仓开始建仓
    if not position_list:
        position_list.update({"B": tick + 1})
        operation_num += 1
        position_list.update({"S": tick - 1})
        operation_num += 1

    #止盈
    if position_list:
        for k, v in position_list.items():
            if k == "B" and (tick - v) >= stop_profit_value:
                #print "多单止盈"
                position_list.pop("B")
                profit_and_loss += (tick - 1) - v
                operation_num += 1
            if k == "S" and (v - tick) >= stop_profit_value:
                #print "空单止盈"
                position_list.pop("S")
                profit_and_loss += v - (tick + 1)
                operation_num += 1

    if len(position_list) == 1:
        for k, v in position_list.items():
            if k == "B" and (v - tick) <= stop_loss_value:
                #print "多单止损"
                position_list.pop("B")
                profit_and_loss += (tick - 1) - v
                operation_num += 1
            if k == "S" and (tick - v) <= stop_loss_value:
                #print "空单止损"
                position_list.pop("S")
                profit_and_loss += v - (tick + 1)
                operation_num += 1
    
    #time.sleep(2)

def test_strategy():
    market_data = create_index_data()
    for i in market_data:
        onTick(i)
    
    return market_data


prof_loss_list = []
win_prof_loss_list = []
for i in range(1, TEST_COUNT):
    fut_data = test_strategy()
    
    print "收盘", fut_data[-1]
    save_close_price(fut_data[-1])
    print "平仓盈亏", profit_and_loss
    print "收盘持仓", position_list
    for k, v in position_list.items():
        if k == "B":
            profit_and_loss += fut_data[-1] - v
        if k == "S":
            profit_and_loss += v - fut_data[-1]

    print "累计盈亏", profit_and_loss
    prof_loss_list.append(profit_and_loss)
    print "操作次数", operation_num/2
    print
    profit_and_loss = 0
    operation_num = 0
    position_list = {}

win_prof_loss_list = [p for p in prof_loss_list if p>0]
print "盈亏列表", prof_loss_list, len(prof_loss_list)
print "累计盈亏", sum(prof_loss_list)
print "盈利列表", win_prof_loss_list, len(win_prof_loss_list)
print "胜率", float(len(win_prof_loss_list))/len(prof_loss_list)*100
