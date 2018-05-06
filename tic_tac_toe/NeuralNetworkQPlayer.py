#
# Copyright 2017 Carsten Friedrich (Carsten.Friedrich@gmail.com). All rights reserved
#
# After a short learning phase this agent plays pretty well against deterministic MinMax.
# There are some hefty swing from always winning to always losing
# After a while in stabilizes at 50 / 50 and then decreases steadily to less then 60 / 40
# Then increases again to 100% draw and seems to stay there
#

import numpy as np
import tensorflow as tf
from tic_tac_toe.TFSessionManager import TFSessionManager as tfsn

from tic_tac_toe.Board import Board, BOARD_SIZE, EMPTY, CROSS, NAUGHT
from tic_tac_toe.Player import Player, GameResult

MODEL_NAME = 'tic-tac-toe-model-nna'
MODEL_PATH = './saved_models/'

WIN_VALUE = 1.0
DRAW_VALUE = 0.6
LOSS_VALUE = 0.0



class QNetwork():

    def __init__(self, name):
        self.learningRate = 0.01
        self.name = name
        self.input_positions = None
        self.target_input = None
        self.logits = None
        self.probabilities = None
        self.train_step = None
        self.build_graph(name)

    def add_layer(self, input_tensor, output_size, regulize=None, name=None):
        input_tensor_size = input_tensor.shape[1].value
        w1 = tf.Variable(tf.truncated_normal([input_tensor_size, output_size],
                                             stddev=0.1 / np.sqrt(float(input_tensor_size * output_size))))
        b1 = tf.Variable(tf.zeros([1, output_size], tf.float32))

        res = tf.matmul(input_tensor, w1) + b1

        if regulize is not None:
            res = regulize(res)

        if name is not None:
            res = tf.identity(res, name)

        return res

    def build_graph(self, name):
        with tf.variable_scope(name):
            self.input_positions = tf.placeholder(tf.float32, shape=(None, BOARD_SIZE * 3), name='inputs')
            self.target_input = tf.placeholder(tf.float32, shape=(None, BOARD_SIZE), name='train_inputs')
            target = self.target_input

            net = self.input_positions
            net = self.add_layer(net, BOARD_SIZE * 3 * 128, tf.nn.relu)

            self.logits = self.add_layer(net, BOARD_SIZE, name='logits')

            self.probabilities = tf.nn.softmax(self.logits, name='probabilities')
            mse = tf.losses.mean_squared_error(predictions=self.logits, labels=target)
            self.train_step = tf.train.GradientDescentOptimizer(learning_rate=self.learningRate).minimize(mse, name='train')


class NNQPlayer(Player):

    def board_state_to_nn_input(self, state):
        res = np.array([(state == self.side).astype(int),
                        (state == Board.other_side(self.side)).astype(int),
                        (state == EMPTY).astype(int)])
        return res.reshape(-1)

    def __init__(self, name):
        self.side = None
        self.board_position_log = []
        self.action_log = []
        self.next_max_log = []
        self.values_log = []
        self.name = name
        self.random_move_prob = 0.1
        self.nn = QNetwork(name)
        self.reward_discount = 0.8
        self.training = True
        super().__init__()

    def new_game(self, side):
        self.side = side
        self.board_position_log = []
        self.action_log = []
        self.next_max_log = []
        self.values_log = []

    def calculate_targets(self):
        game_length = len(self.action_log)
        targets = []

        for i in range(game_length - 1, -1, -1):
            target = np.copy(self.values_log[i])

            target[self.action_log[i]] = self.reward_discount * self.next_max_log[i]
            targets.append(target)

        targets.reverse()

        return targets

    def get_probs(self, input_pos):
        probs, logits = tfsn.get_session().run([self.nn.probabilities, self.nn.logits],
                                 feed_dict={self.nn.input_positions: [input_pos]})
        return probs[0], logits[0]

    def move(self, board):
        self.board_position_log.append(board.state.copy())
        nn_input = self.board_state_to_nn_input(board.state)

        probs, logits = self.get_probs(nn_input)

        logits = np.copy(logits)

        for index, p in enumerate(probs):
            if not board.is_legal(index):
                probs[index] = 0
                logits[index] = 0

        if len(self.action_log) > 0:
            self.next_max_log.append(np.max(logits))

        self.values_log.append(np.copy(logits))

        probs = [p / sum(probs) for p in probs]
        if self.training and np.random.rand(1) < self.random_move_prob:
            move = np.random.choice(BOARD_SIZE, p=probs)
        else:
            move = np.argmax(probs)

        _, res, finished = board.move(move, self.side)

        self.action_log.append(move)

        return res, finished

    def final_result(self, result):
        if (result == GameResult.NAUGHT_WIN and self.side == NAUGHT) or (
                result == GameResult.CROSS_WIN and self.side == CROSS):
            reward = WIN_VALUE  # type: float
        elif (result == GameResult.NAUGHT_WIN and self.side == CROSS) or (
                result == GameResult.CROSS_WIN and self.side == NAUGHT):
            reward = LOSS_VALUE  # type: float
        elif result == GameResult.DRAW:
            reward = DRAW_VALUE  # type: float
        else:
            raise ValueError("Unexpected game result {}".format(result))

        self.next_max_log.append(reward)
        self.random_move_prob = 0.95 * self.random_move_prob

        if self.training:
            targets = self.calculate_targets()
            nn_input = [self.board_state_to_nn_input(x) for x in self.board_position_log]
            # for target, current_board, old_probs, old_action in zip(targets, self.board_position_log,
            #                                                         self.values_log, self.action_log):
            #     nn_input = self.board_state_to_nn_input(current_board)

            tfsn.get_session().run([self.nn.train_step],
                     feed_dict={self.nn.input_positions: nn_input, self.nn.target_input: targets})
