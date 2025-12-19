import string
from collections import Counter


def counterSubset(list1, list2):
    c1, c2 = Counter(list1), Counter(list2)
    for k, n in c1.items():
        if n > c2[k]:
            return False
    return True


def expectedEliminated(word, word_list):
    total_score = 0
    total_words = len(word_list)
    distinct_letters = set(word)
    for letter in distinct_letters:
        words_removed = sum([letter in word for word in word_list])
        total_score += 2 * words_removed * (1 - (words_removed / total_words))
    return total_score / len(word)


# get valid words from text file
word_file = open("word_list.txt", "r")
content = word_file.read()
wordle_words = content.replace('"', "").split(",")
word_file.close()

all_letters = set(string.ascii_lowercase)
eliminated_letters = set()
found_letters = []
wrong_position = [set(), set(), set(), set(), set()]
solved_letters = ["", "", "", "", ""]

guesses = []
result_input = ""
print()

while result_input.lower() != "ggggg":

    guess_input = input("Guess? ")
    result_input = input("Result? ")
    guesses.append((guess_input.lower(), result_input.lower()))

    if result_input.lower() == "ggggg":
        print("Congrats!!")
        print()
        continue

    for guess, result in guesses:
        found_letters = []
        for i, r in enumerate(result):
            if r == "g":
                found_letters.append(guess[i])
                solved_letters[i] = guess[i]
            elif r == "y":
                found_letters.append(guess[i])
                wrong_position[i].add(guess[i])
            else:
                eliminated_letters.add(guess[i])

    valid_letters = all_letters.difference(eliminated_letters)

    possibles = []
    for i, letters in enumerate(wrong_position):
        if solved_letters[i] == "":
            possibles.append(valid_letters.difference(letters))
        else:
            possibles.append(set(solved_letters[i]))

    valid_words = []

    for word in wordle_words:
        possibles_matched = all(
            [letter in possibles[ind] for ind, letter in enumerate(word)]
        )
        has_all_found_letters = counterSubset(found_letters, word)
        if possibles_matched and has_all_found_letters:
            valid_words.append(word)

    patterns = []
    for word in valid_words:
        pattern = list(word)
        for i in range(5):
            if solved_letters[i] != "":
                pattern[i] = "_"
        patterns.append(pattern)

    valid_guesses = []
    for word in valid_words:
        new_letters = []
        for i in range(5):
            if solved_letters[i] == "":
                new_letters.append(word[i])
        valid_guesses.append((word, expectedEliminated(new_letters, patterns)))

    valid_guesses.sort(key=lambda x: x[1], reverse=True)
    print()
    print(len(valid_words), "possible remaining. Best next guesses:")
    for a, b in valid_guesses[:5]:
        average_expected_removed = "{:.3f}".format(len(valid_guesses) - b)
        print(a, "- Average Expected Removed: ", average_expected_removed)
    print()

