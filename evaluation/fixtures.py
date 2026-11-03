"""Controlled exercises, never copied learner records. Not model-quality results."""
import copy


def exercise(topic):
    fixtures={
        'get':('Find the requested score','Return the score for name, or zero when the key is absent. Do not change scores.','score_for','scores, name','return scores.get(name, 0)','return scores[name]',[([{'Mia':95},'Mia'],95),([{},'Ava'],0),([{'Leo':8},'Leo'],8)]),
        'range':('Numbers below a boundary','Return a list of integers from zero up to, but excluding, stop. The input stop is a nonnegative integer.','below','stop','result = []\nfor n in range(stop):\n    result.append(n)\nreturn result','result = []\nfor n in range(stop + 1):\n    result.append(n)\nreturn result',[([3],[0,1,2]),([0],[]),([1],[0])]),
        'break':('Sizes after an inner scan','For each list in rows, scan until a positive item is found, then collect that row length. Return every row length in order. Do not change rows.','row_sizes','rows','sizes = []\nfor row in rows:\n    for value in row:\n        if value > 0:\n            break\n    sizes.append(len(row))\nreturn sizes','return []',[([[[1,2],[3]]],[2,1]),([[]],[]),([[[0],[0,2,3]]],[1,3])]),
        'case':('Read an airport city','Return the city for the supplied exact airport code in airports. All supplied airport codes exist. Do not change airports.','airport_city','airports, code','return airports[code]["city"]','return airports[code]["City"]',[([{'LHR':{'city':'London'}},'LHR'],'London'),([{'HND':{'city':'Tokyo'}},'HND'],'Tokyo'),([{'JFK':{'city':'New York'}},'JFK'],'New York')]),
        'alias':('Append without changing the input','Return a new list containing values followed by item. Do not change the original values list.','with_item','values, item','result = values.copy()\nresult.append(item)\nreturn result','result = values\nresult.append(item)\nreturn result',[([[1,2],3],[1,2,3]),([[],5],[5]),([[9],0],[9,0])]),
        'return':('Return twice the value','Return twice the supplied number as a number. Printing the answer alone does not meet this contract.','twice','number','return number * 2','print(number * 2)',[([3],6),([0],0),([-2],-4)]),
        'index':('Read the third item','Return the third item of values. Each supplied list has at least three items. Do not change values.','third','values','return values[2]','return values[3]',[([['A','B','C','D']],'C'),([[7,8,9]],9),([[0,2,4,6]],4)]),
        'while':('Count down through one','Return a countdown list starting at the nonnegative integer start and ending at one. For zero return an empty list.','countdown','start','result = []\nn = start\nwhile n > 0:\n    result.append(n)\n    n = n - 1\nreturn result','result = []\nn = start\nwhile n > 1:\n    result.append(n)\n    n = n - 1\nreturn result',[([3],[3,2,1]),([0],[]),([1],[1])]),
        'continue':('Skip negative items','Return the nonnegative numbers from values in their original order. Skip negative items and continue scanning later items. Do not change values.','nonnegative','values','result = []\nfor value in values:\n    if value < 0:\n        continue\n    result.append(value)\nreturn result','result = []\nfor value in values:\n    if value < 0:\n        break\n    result.append(value)\nreturn result',[([[2,-1,3]],[2,3]),([[]],[]),([[-5,0,4]],[0,4])])}
    title,instructions,entry,parameters,reference,broken,cases=fixtures[topic]
    def source(body):return f'def {entry}({parameters}):\n'+''.join('    '+line+'\n' for line in body.splitlines())
    spec={'title':title,'instructions':instructions,'entry':entry,'starter':source('pass'),'reference_solution':source(reference),'preserve_input':True,
        'cases':[{'arguments':args,'expected':expected} for args,expected in cases],'sources':['video-eval-'+topic]}
    return copy.deepcopy(spec),source(broken)


def lesson(topic,passages):
    task,broken=exercise(topic);identifier='video-eval-'+topic;part=next(p for p in passages if p['id']==identifier)
    code='count = 2\nprint(count)'
    unit={'id':'controlled-'+topic,'title':task['title'],'explanation':part['text'],'opening_question':'What result do you expect from the code you are about to run?',
        'sources':[identifier],'quiz':[{'kind':'concept','prompt':'Does this optional check establish independent mastery?','code':'','options':['No','Yes, always','Only when skipped'],'answer_index':0,'expected_output':'','explanation':'A formative quiz is practice, not independent evidence of mastery.','sources':[identifier]}],
        'prediction':{'prompt':'What does this small setup display?','code':code,'options':['1','2','3'],'expected_output':'2','explanation':'The supplied literal value is displayed. This setup is a controlled evaluation fixture.','sources':[identifier]},'exercise':task}
    quote=part['text'].split('. ')[0]+'.'
    return {'title':'Controlled tutor evaluation: '+topic,'answer':'## Controlled evaluation fixture\n\n'+part['text']+'\n\nThis operator-authored scenario tests tutor decisions, source provenance and checked practice. It is not a generated video lesson or a student learning outcome.',
        'sources':[identifier],'units':[unit],'evidence_quotes':[{'source_id':identifier,'claim':part['text'].split('. ')[0]+'.','quote':quote}]},broken
