from random import choice
import os
import json

# Settings you change
card_folder = 'cards'
answer_cards_file_names = ['answer_cards', 'custom_anwser_cards']
question_cards_file_name = ['question_cards', 'question_cards1', 'question_cards2', 'custom_question_cards']

# Settings that are used
base_directory = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath("."))))


class Deck(object):
    def __init__(self):
        self.answerDb = self.parse_card_file('answer')
        self.questionDb = self.parse_card_file('question')

    def parse_card_file(self, card_type):
        card_type_map = {'answer': answer_cards_file_names, 'question': question_cards_file_name}

        # Read text file into a list containing only strings of text for the card
        card_text_list = []
        for file_name in card_type_map[card_type]:
            path = os.path.abspath(os.path.join(base_directory, card_folder, file_name))
            if os.path.exists(path):
                with open(path) as file_handle:
                    file_data = file_handle.readlines()
                card_text_list.extend(file_data)
        if len(card_text_list) is 0:
            raise IOError

        # Deduplicate the text from the cards
        card_text_list = list(set(card_text_list))

        # Turn the strings of text into a Card object
        card_object_list = []
        for index, card in enumerate(card_text_list):
            # Prepare card text by removing control chars
            card = card.rstrip()
            # Figure out how many answers are required for a question card
            if card_type == 'question':
                answers = self.count_answers(card)
                card_object_list.append(Card(index, card_type, card, answers=answers))
            else:
                card_object_list.append(Card(index, card_type, card))
        return card_object_list

    def count_answers(self, text, blank_format = '__________'):
        blanks = text.count(blank_format)
        if blanks is 0:
            return 1
        else:
            return blanks

    def drawCard(self, typeOfCard):
        typeMap = {'answer': self.answerDb, 'question': self.questionDb}
        type = typeMap[typeOfCard]
        card = choice(type)
        type.remove(card)
        return card

    def __repr__(self):
        return json.dumps({'questions': len(self.questionDb), 'answers': len(self.answerDb)})

class Card(object):
    def __init__(self, id, type, text, **kwargs):
        self.id = id
        self.type = type
        self.text = text
        for key, value in kwargs.iteritems():
            setattr(self, key, value)

class Game(object):
    def __init__(self, players, round_limit = 5, rule_set="house"):
        self.round_limit = round_limit
        self.deck = Deck()
        self.players = self.build_player_list(players)
        self.round = None
        self.question = None

    def build_player_list(self, players):
        player_list = {}
        for player in players:
            player_list[player] = PlayerHand(self.deck)
        return player_list

    def next_round(self):
        if self.round is None:
            self.round = 0
        if self.round < self.round_limit:
            self.round = self.round + 1
        else:
            raise IndexError

        self.question = self.deck.drawCard('question')
        return {'question': self.question, 'hands': self.players}

    def displayAnswer(self):
        pass

    def cardSubmit(self):
        for player in self.players:
            cardInput = None
            cardRange = range(5)
            while cardInput not in cardRange:
                try:
                    cardInput = int(raw_input('%s Pick a Card: ' % player)) - 1
                except ValueError:
                    pass

class Round(object):
    def __init__(self, deck, players):
        self.question = deck.drawCard('question')
        self.players = players

class PlayerHand(object):
    def __init__(self, deck):
        self.card_list = self.dealHand(deck)

    def dealHand(self, deck):
        hand = []
        while len(hand) < 5:
            card = deck.drawCard('answer')
            hand.append(card)
        return hand
            
    def showHand(self):
        for index, card in enumerate(self.card_list):
            print '%s: %s' % (index + 1, card.text)




if __name__=="__main__":
    game = Game(['Bear','Swim', 'Jazz'])
    print "\nGame started with the following players: %s \n" % game.players.keys()
    round = game.next_round()
    print "The first question is: %s \n" % game.question.text

    print "Swim's hand the easy way:"
    game.players['Swim'].showHand()

    print "\nJazz's hand in a weird way"
    round['hands']['Jazz'].showHand()

    print "\nBear's hand the hard way:"
    for index, card in enumerate(round['hands']['Bear'].card_list):
        print '%s: %s' % (index + 1, card.text)



