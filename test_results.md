# LLM Evaluation & Benchmark Report
Generated at: 2026-10-19 16:57:36

## Summary Comparison
| Model | Pass Rate | Assertions Passed | Avg Generation Speed | Total Latency |
| :--- | :--- | :--- | :--- | :--- |
| **qwen2.5-coder** | 84.2% | 16/19 | 5.76 tok/s | 48.99s |

## Detailed Test Results

### Model: `qwen2.5-coder`

#### ❌ FAIL [math-1] Basic Addition (1+1)
- **Question**: What is 1 + 1? Answer in one short sentence.
- **Answer**: `1 + 1 is 2.`
- **Performance**: Latency: `29.581s` | Speed: `1.09 tok/s` | Tokens: `37+9`
- **Rule Assertions**:
  - [✓] Contains match '2' (any of ['2', 'two'])
  - [✓] Does not contain prohibited 'error'
  - [✗] Latency 29.58s exceeded limit of 15.00s

#### ✅ PASS [fact-france] Capital of France
- **Question**: What is the capital city of France?
- **Answer**: `The capital city of France is Paris.`
- **Performance**: Latency: `0.749s` | Speed: `20.79 tok/s` | Tokens: `33+9`
- **Rule Assertions**:
  - [✓] Contains 'Paris'
  - [✓] Does not contain prohibited 'London'
  - [✓] Does not contain prohibited 'Berlin'

#### ✅ PASS [code-even] Python Even Number Function
- **Question**: Write a Python function named `is_even` that takes an integer and returns True if it is even, False otherwise.
- **Answer**: `Certainly! Below is a Python function named `is_even` that takes an integer as input and returns `True` if the number is even, and `False` otherwise.

```python
def is_even(number):
    """
    Determines if the given number is even.

    Args:
    number (int): The number to check.

    Returns:
    bool: True if the number is even, False otherwise.
    """
    return number % 2 == 0
```

You can use this function to check if a number is even by calling it with an integer argument. For example:

```python
print(is_even(4))  # Output: True
print(is_even(7))  # Output: False
````
- **Performance**: Latency: `8.531s` | Speed: `18.75 tok/s` | Tokens: `49+149`
- **Rule Assertions**:
  - [✓] Matches regex pattern: r'def\s+is_even\s*\([^)]*\).*?:'
  - [✓] Contains all: ['def is_even', 'return', '%']

#### ✅ PASS [logic-bool] Boolean Logic
- **Question**: If all roses are flowers and some flowers fade quickly, can we be certain that all roses fade quickly? Answer Yes or No and briefly explain.
- **Answer**: `No. 

Explanation: The statement "all roses are flowers" establishes a subset relationship, where roses are a type of flower. The statement "some flowers fade quickly" tells us that there is at least one flower that fades quickly. However, it does not provide any information about the fading rate of roses specifically. Therefore, we cannot conclude that all roses fade quickly based on the given information.`
- **Performance**: Latency: `4.759s` | Speed: `19.2 tok/s` | Tokens: `52+80`
- **Rule Assertions**:
  - [✓] Contains match 'No' (any of ['No', 'cannot be certain', 'not necessarily'])
  - [✓] Latency 4.76s <= limit 15.00s

#### ✅ PASS [format-color] Single Word Answer
- **Question**: What color is the clear sky on a sunny day? Answer with exactly one word.
- **Answer**: `Blue`
- **Performance**: Latency: `0.66s` | Speed: `37.37 tok/s` | Tokens: `44+2`
- **Rule Assertions**:
  - [✓] Contains 'blue'
  - [✓] Latency 0.66s <= limit 5.00s

#### ❌ FAIL [hard-count-r] Letter Counting (Strawberry)
- **Question**: How many times does the letter 'r' appear in the word 'strawberry'? Answer with only the digit and no other words or punctuation.
- **Answer**: `2`
- **Performance**: Latency: `0.639s` | Speed: `37.41 tok/s` | Tokens: `50+2`
- **Rule Assertions**:
  - [✗] Expected exact match '3', got '2'

#### ✅ PASS [hard-decimal-cmp] Decimal Comparison (9.11 vs 9.9)
- **Question**: Which number is strictly greater: 9.11 or 9.9? Answer with only the number and nothing else.
- **Answer**: `9.9`
- **Performance**: Latency: `0.744s` | Speed: `25.37 tok/s` | Tokens: `49+4`
- **Rule Assertions**:
  - [✓] Exact match: '9.9'
  - [✓] Does not contain prohibited '9.11'

#### ✅ PASS [hard-bat-ball] Bat and Ball Math Trap
- **Question**: A bat and a ball cost $1.10 in total. The bat costs $1.00 more than the ball. How many cents does the ball cost? Answer with only the number of cents.
- **Answer**: `5`
- **Performance**: Latency: `0.84s` | Speed: `37.38 tok/s` | Tokens: `68+2`
- **Rule Assertions**:
  - [✓] Exact match: '5'
  - [✓] Does not contain prohibited '10'

#### ✅ PASS [hard-no-e] Negative Constraint (Zero 'e's)
- **Question**: Write a complete sentence describing a cat. Do NOT use the letter 'e' anywhere in your response. The letter 'e' or 'E' must not appear at all.
- **Answer**: `A cat is a small, furry animal with sharp claws and a bushy tail.`
- **Performance**: Latency: `1.581s` | Speed: `20.08 tok/s` | Tokens: `66+18`
- **Rule Assertions**:
  - [✓] Does not contain prohibited 'e'

#### ❌ FAIL [hard-reverse-word] Word Reversal (KNOWLEDGE)
- **Question**: Reverse the letters of the word 'KNOWLEDGE'. Answer with only the reversed word in all-capital letters.
- **Answer**: `EGODLEWONK`
- **Performance**: Latency: `0.905s` | Speed: `22.22 tok/s` | Tokens: `45+7`
- **Rule Assertions**:
  - [✗] Expected exact match 'EGDELWONK', got 'EGODLEWONK'
