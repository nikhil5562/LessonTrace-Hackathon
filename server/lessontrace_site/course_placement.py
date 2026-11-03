"""Small authored placement checks, explicitly not model-generated course notes."""
import copy
from .course_catalog import topic,allowed_concepts

PLACEMENT={'variables','arithmetic','strings','comparisons','lists','indexing','list_mutation','if_else'}
_ITEMS={
    'variables':(['value'],'result = value','Assign the supplied value to result.',[[3],[8],[0]],[3,8,0],['source'],'result = source','Assign the supplied source value to result.',[[6],[-2],[11]],[6,-2,11]),
    'arithmetic':(['left','right'],'result = left + right','Assign the sum of left and right to result.',[[2,3],[0,4],[-2,2]],[5,4,0],['start','decrease'],'result = start - decrease','Assign start reduced by decrease to result.',[[9,2],[3,5],[0,0]],[7,-2,0]),
    'strings':(['prefix','suffix'],'result = prefix + suffix','Join prefix followed by suffix into the result string.',[['Py','thon'],['','hi'],['a','b']],['Python','hi','ab'],['text'],'result = len(text)','Assign the length of text to result.',[['hello'],[''],['xy']],[5,0,2]),
    'comparisons':(['left','right'],'result = left > right','Set result to whether left is strictly greater than right.',[[4,2],[2,4],[3,3]],[True,False,False],['value','limit'],'result = value <= limit','Set result to whether value is at most limit.',[[5,5],[2,4],[9,3]],[True,True,False]),
    'lists':(['first','second'],'result = [first, second]','Make result a list holding first and second in that order.',[[2,3],[0,4],[8,8]],[[2,3],[0,4],[8,8]],['a','b'],'result = [b, a]','Make result a list holding b and then a.',[[9,2],[3,5],[0,1]],[[2,9],[5,3],[1,0]]),
    'indexing':(['values'],'result = values[1]','Assign the second item of values to result. Each input list has at least two items.',[[[2,5]],[[8,1,4]],[[0,9]]],[5,1,9],['items'],'result = items[0]','Assign the first item of the nonempty items list to result.',[[[4,7]],[[6]],[[2,3,8]]],[4,6,2]),
    'list_mutation':(['values','item'],'result = values.copy()\nresult.append(item)','Make a new list named result with values followed by item. Preserve values.',[[[2],3],[[],4],[[0,1],9]],[[2,3],[4],[0,1,9]],['items','last'],'result = items.copy()\nresult.append(last)','Return the items followed by last in a new result list. Preserve items.',[[[9,2],5],[[],0],[[3],8]],[[9,2,5],[0],[3,8]]),
    'if_else':(['number'],'if number > 0:\n    result = "positive"\nelse:\n    result = "other"','Set result to positive for a number above zero, or other otherwise. Use if and else.',[[2],[0],[-3]],['positive','other','other'],['score'],'if score >= 5:\n    result = "ready"\nelse:\n    result = "again"','Set result to ready for score of at least five, or again otherwise. Use if and else.',[[5],[8],[4]],['ready','ready','again'])}


def artifact(concept):
    if concept not in PLACEMENT:raise ValueError('This outlined topic does not yet have a placement check.')
    item=topic(concept);needs=sorted(allowed_concepts(concept)-{concept});source='hub-placement-'+concept
    parameters,code,instructions,args,expected,fparams,fcode,finstructions,fargs,fexpected=_ITEMS[concept]
    def exercise(names,reference,text,arguments,results):return {'kind':'program','parameters':names,'entry':'result','title':item['title']+' check','instructions':text+' Inputs are supplied separately for each check; do not overwrite them.','starter':'result = None','reference_solution':reference,'preserve_input':True,
        'cases':[{'arguments':a,'expected':r} for a,r in zip(arguments,results)],'sources':[source],'needs':needs,'targets':[concept]}
    prediction={'prompt':'What does this setup print?','code':'value = 3\nprint(value)','options':['2','3','4'],'expected_output':'3','answer_index':1,'explanation':'The printed value is the assigned three. This is an original placement check, not a mastery claim.','sources':[source],'needs':[],'targets':[concept]}
    question={'kind':'complete_code','prompt':'Choose the expression that prints the supplied value.','code':'value = 7\nprint(___)','options':['value','0','1'],'answer_index':0,'expected_output':'7','explanation':'The name value reads the value assigned in this shown setup.','sources':[source],'needs':[],'targets':[concept],'purpose':'practice'}
    unit={'id':'placement-'+concept.replace('_','-'),'title':item['title'],'explanation':'This is a short prerequisite check for a skill you may already know. Solve the tasks yourself. Passing its checks records evidence for course prerequisites; it does not certify lasting mastery.',
        'opening_question':'What result should your program produce for the supplied inputs?','sources':[source],'quiz':[question],'prediction':prediction,
        'exercise':exercise(parameters,code,instructions,args,expected),'fresh_exercise':exercise(fparams,fcode,finstructions,fargs,fexpected)}
    return {'version':'placement-v1','concept_id':concept,'title':item['title'],'provider':'local_check','model':None,'role':'placement',
        'curriculum':{'title':item['title']+' · prerequisite check','answer':'## Check a skill you already know\n\nThis is an original prerequisite assessment, not an AI lesson. Complete the output questions and the main program, then try a different program without tutor help. A successful attempt is evidence for practice eligibility, not a claim of mastery.','sources':[source],'units':[unit]},
        'caption_chunks':[{'id':source,'text':'Original LessonTrace placement checks use actual Python output and program results. They are not extracted video captions.','source_id':'placement','source_title':'LessonTrace · Original prerequisite checks','kind':'web','url':'https://docs.python.org/3/tutorial/','start':None,'end':None,'heading':'Original assessment; reference for optional study'}],
        'source_documents':[],'review_status':'authored-checks'}
