"""Original sample using the same quiz, tutor and bounded Python APIs as the product."""
import time
import uuid
from fastapi import HTTPException,Request
from fastapi.responses import PlainTextResponse
from .video_curriculum import validate_lesson
from .video_learning import blank_progress,progress_key
from .video_lessons import public_session

SOURCE_ID='hub-lessontrace-original-break-0001'
SOURCE='''Original LessonTrace sample, written during the hackathon.
In nested loops, break exits only the nearest enclosing loop. The outer loop can continue with its next item. A second break placed in the outer body stops that outer loop. The indentation and the actual reached line determine which loop stops.
A function returns its result to its caller. Appending a value changes that list. A loop over an empty list executes its body zero times. An outer list may contain empty rows; the inner loop simply has no values for those rows.
The example uses groups A and B, each with values 1 and 2. Its break is inside the inner loop, so each group prints only its first value. These are original examples, not a copied lecture or a claim that quiz performance proves mastery.'''
PREDICTION='for group in ["A", "B"]:\n    for value in [1, 2]:\n        print(group, value)\n        break'
REFERENCE='def first_in_each(rows):\n    firsts = []\n    for row in rows:\n        for number in row:\n            firsts.append(number)\n            break\n    return firsts'
STARTER='def first_in_each(rows):\n    firsts = []\n    for row in rows:\n        for number in row:\n            firsts.append(number)\n            break\n        break\n    return firsts'

def authored_lesson():
    exercise={'title':'Keep the first value from every nonempty row','instructions':'Return a list with the first value from every nonempty row, in row order. Keep rows unchanged. The starter stops too early: find and fix its loop-control mistake. Empty rows contribute no value.',
        'entry':'first_in_each','starter':STARTER,'reference_solution':REFERENCE,'preserve_input':True,
        'cases':[{'arguments':[[[4,8],[5,9]]],'expected':[4,5]},{'arguments':[[]],'expected':[]},{'arguments':[[[],[3],[2,1]]],'expected':[3,2]}],'sources':[SOURCE_ID]}
    unit={'id':'original-inner-break','title':'Which loop does this break stop?',
        'explanation':'A break exits its nearest enclosing loop. Here the outer loop chooses a group, then the inner loop chooses a value. Follow one loop finger at a time. These original prepared notes are not represented as freshly generated AI content.',
        'opening_question':'If an inner loop stops, does that necessarily stop its outer loop?','sources':[SOURCE_ID],
        'quiz':[{'kind':'concept','prompt':'An inner-loop break is reached. Which loop exits immediately?','code':PREDICTION,'options':['Only the inner loop','Every enclosing loop','Neither loop'],
            'answer_index':0,'expected_output':'','explanation':'The reached break belongs to the inner loop. The outer loop can take its next group.','sources':[SOURCE_ID]}],
        'prediction':{'prompt':'Predict the printed output before running this original example.','code':PREDICTION,'options':['A 1\nB 1','A 1','A 1\nA 2\nB 1\nB 2'],
            'expected_output':'A 1\nB 1','explanation':'Each group reaches its first inner value and breaks only that inner loop.','sources':[SOURCE_ID]},'exercise':exercise}
    return {'title':'Original demo: two loops, one confusing break','answer':'## An original sample\n\n'+SOURCE+'\n\n```python\n'+PREDICTION+'\n```\n\nPredict the result, then run and inspect actual Python. The coding task has a separate deliberate error. Ask the live Meta tutor for a hint after making your own attempt.',
        'sources':[SOURCE_ID],'units':[unit],'evidence_quotes':[{'source_id':SOURCE_ID,'claim':'A break stops its nearest enclosing loop.','quote':'break exits only the nearest enclosing loop.'}]}

def install_demo_routes(app,owner,store,execution,semaphore,coach):
    @app.get('/demo/source.txt')
    async def original_source():return PlainTextResponse(SOURCE)

    @app.post('/api/demo/start')
    async def start(request:Request):
        who=owner(request,True)
        if not execution.ready:raise HTTPException(503,'Python is warming up. Retry the original demo when Python is ready.')
        source_url=str(request.base_url).rstrip('/')+'/demo/source.txt'
        chunks=[{'id':SOURCE_ID,'source_id':'lessontrace-original','source_title':'LessonTrace original workshop source','kind':'web','url':source_url,
            'start':None,'end':None,'heading':'Nearest-loop control','text':SOURCE}]
        async with semaphore:curriculum=await validate_lesson(authored_lesson(),execution,[SOURCE_ID],chunks)
        record={'context':'hub','original_demo':True,'lesson_id':uuid.uuid4().hex,'interactive':True,'title':curriculum['title'],'answer':curriculum['answer'],
            'sources':[SOURCE_ID],'curriculum':curriculum,'caption_chunks':chunks,'source_documents':[{'id':'lessontrace-original','title':'LessonTrace original workshop source','url':source_url,'kind':'web'}],
            'video_id':'original001','url':source_url,'caption_source':'Original operator-authored source, not a video transcript','language':'en','auto_generated':False,
            'created':time.time(),'coverage':'Original prepared demonstration. Python runs are real. Meta tutoring is live only when enabled; recorded examples are labelled.',
            'provider':'prepared-original','model':None,'practice_basis':'Original deliberate loop-control bug; actual Python checks.'}
        previous=store.progress(who).get('hub_session')
        if previous:coach.remember(who,previous)
        store.set_progress(who,'hub_session',record);store.set_progress(who,progress_key(record['lesson_id']),blank_progress(record));coach.remember(who,record)
        return {'session':public_session(record),'mode':'original-prepared-source','meta_calls':0}
