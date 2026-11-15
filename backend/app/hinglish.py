"""Offline Hindi Devanagari -> readable Roman Hindi captions.

Not a translation service. Existing English/Roman tokens are preserved. Word
boundaries and timestamps remain intact. Romanization is best-effort and users
should review names and unusual colloquialisms before publishing.
"""
import re

# Common colloquial spellings win over mechanical transliteration.
COMMON = {
    'नमस्ते':'namaste','दोस्तों':'dosto','दोस्तो':'dosto','दोस्त':'dost',
    'कैसे':'kaise','कैसी':'kaisi','कैसा':'kaisa','हो':'ho','है':'hai',
    'हैं':'hain','हूं':'hoon','हूँ':'hoon','मैं':'main','हम':'hum','तुम':'tum',
    'आप':'aap','क्या':'kya','क्यों':'kyun','कौन':'kaun','कहाँ':'kahan',
    'कहा':'kaha','आज':'aaj','कल':'kal','अभी':'abhi','यह':'yeh','ये':'ye',
    'वह':'woh','वो':'wo','बहुत':'bahut','अच्छा':'accha','अच्छी':'acchi',
    'नहीं':'nahi','नही':'nahi','जी':'ji','बात':'baat','करेंगे':'karenge',
    'कर':'kar','करते':'karte','रहे':'rahe','रहा':'raha','रही':'rahi',
    'हेलो':'hello','हैलो':'hello','भाई':'bhai','लोग':'log','सभी':'sabhi',
    'मुझे':'mujhe','तुझे':'tujhe','पता':'pata','तो':'to','से':'se',
    'में':'mein','को':'ko','का':'ka','की':'ki','के':'ke','और':'aur',
    'लेकिन':'lekin','अगर':'agar','फिर':'phir','लिए':'liye','यहाँ':'yahan',
    'देखो':'dekho','देख':'dekh','सुनो':'suno','वीडियो':'video',
}
VOWELS = dict(zip('अआइईउऊऋएऐओऔ', ['a','aa','i','ee','u','oo','ri','e','ai','o','au']))
MATRAS = dict(zip('ािीुूृेैोौ', ['aa','i','ee','u','oo','ri','e','ai','o','au']))
CONSONANTS = {
 'क':'k','ख':'kh','ग':'g','घ':'gh','ङ':'ng','च':'ch','छ':'chh','ज':'j','झ':'jh','ञ':'ny',
 'ट':'t','ठ':'th','ड':'d','ढ':'dh','ण':'n','त':'t','थ':'th','द':'d','ध':'dh','न':'n',
 'प':'p','फ':'ph','ब':'b','भ':'bh','म':'m','य':'y','र':'r','ल':'l','व':'v',
 'श':'sh','ष':'sh','स':'s','ह':'h','ळ':'l','क़':'q','ख़':'kh','ग़':'g','ज़':'z','फ़':'f','ड़':'d','ढ़':'dh',
}
SIGNS = {'ं':'n','ँ':'n','ः':'h','ऽ':'','़':''}
TOKEN = re.compile(r'[\u0900-\u097F]+|[^\u0900-\u097F]+')


def roman_word(word: str) -> str:
    if word in COMMON:
        return COMMON[word]
    out=[]
    i=0
    while i<len(word):
        ch=word[i]
        if ch in CONSONANTS:
            out.append(CONSONANTS[ch]); i+=1
            if i<len(word) and word[i]=='़': i+=1
            if i<len(word) and word[i]=='्':
                i+=1  # no inherent vowel before conjunct
            elif i<len(word) and word[i] in MATRAS:
                out.append(MATRAS[word[i]]); i+=1
            elif i<len(word) and word[i] in 'ंँ':
                out.append('a')
            elif i<len(word) and word[i] in CONSONANTS:
                out.append('a')
            elif i<len(word) and word[i] not in '।,.!?':
                # A conservative mid-word schwa; common words handled above.
                out.append('a')
        elif ch in VOWELS: out.append(VOWELS[ch]); i+=1
        elif ch in SIGNS: out.append(SIGNS[ch]); i+=1
        elif ch=='्': i+=1
        else: out.append(ch); i+=1
    return ''.join(out)


def romanize(text: str) -> str:
    """Preserve punctuation, Roman script, numbers, and exact token timing."""
    return ''.join(roman_word(token) if '\u0900' <= token[0] <= '\u097f' else token
                   for token in TOKEN.findall(text))
