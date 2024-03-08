import random

START = 2500

def generate_random_number(start, step, swing):
    global START
    choice_list = [0, step, (0 - step)]
    if start < START * (1 - swing):
        return start + 1
    if start > START * (1 + swing):
        return start - 1
    return start + random.choice(choice_list)

def create_index_data():
    swing = random.choice([0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.09])
    random_number_list = []
    global START
    start = START
    print "start", start
    print "swing", swing
    for i in range(43200):
        start = generate_random_number(start, 1, swing)
        random_number_list.append(start)

    step_list = []
    for i in range(1, len(random_number_list)):
        step_list.append(random_number_list[i] - random_number_list[i - 1])

    index_list = []
    for i in range(len(step_list)):
        index_list.append((random_number_list[i], step_list[i]))
    print index_list
    print
    print "max", max(random_number_list)
    print "min", min(random_number_list)

for i in range(10):
    create_index_data()
    print
