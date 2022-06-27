from enum import auto, Enum

from sentence_transformers import SentenceTransformer, util
from transformers import pipeline
from wit import Wit
from text2system.auxiliary.enums.intent import Intent

from text2system.config import (PNL_GENERAL_THRESHOLD,
                                WIT_ACCESS_KEY)

class EntityType(Enum):#TODO: #15 to change name to differ from entity.py
    ATTRIBUTE = auto()
    CLASS = auto()
    CONTACT = auto()
    EMAIL = auto()
    LOCATION = auto()

class Entity:
    def __init__(self, _type, body, role, start) -> None:
        self.type = _type
        self.body = body
        self.role = role
        self.start = start
        if self.role == 'attribute_name':
            self.body = self.body.lower().strip().replace(' ', '_')
class WITParser:
    def __init__(self, response) -> None:
        self.__intent = None
        self.__entities = []
        
        if (len(response['intents'])>0
            and response['intents'][0]['confidence'] > PNL_GENERAL_THRESHOLD):
                self.__intent = Intent(response['intents'][0]['name'].upper().replace('WIT$',''))

        #print(json.dumps(response, indent=3))
        for key in response['entities']:
            for entity in response['entities'][key]:
                if entity['confidence'] > PNL_GENERAL_THRESHOLD:
                    new_ent = Entity(EntityType(entity['name'].replace('wit$','').upper())
                                     , entity['body']
                                     , entity['role']
                                     , entity['start'])
                    self.__entities.append(new_ent)
        
        self.__entities.sort(key=lambda x: x.start)



    def getEntities(self) -> list:
        return self.__entities
    
    def getEntitiesByType(self, entityType):
        listReturn = []
        for entity in self.getEntities():
            if entity.type == entityType:
                listReturn.append(entity)
        return listReturn
    
    def getEntities_ATTRIBUTE(self):
        return self.getEntitiesByType(EntityType.ATTRIBUTE)    
class AIEngine:
    #Wrapper class for encapsulate parsing services
    class __MsgParser:
        def __init__(self, user_msg, aie_obj) -> None:
            self.user_msg = user_msg
            self.__aie_obj = aie_obj
            self.intent = None
            
            #pos-tagging the user_msg
            self.tokens =aie_obj.posTagMsg(user_msg)
            
            #build a tokens type map
            self.tokens_bytype_map = {}
            for token in self.tokens:
                if not(token['entity'] in self.tokens_bytype_map):
                    self.tokens_bytype_map[token['entity']] = []
                self.tokens_bytype_map[token['entity']].append(token)
            
            considered_msg = self.user_msg
            candidate_labels=[str(e) for e in Intent]
            first_verb = self.getFirstTokenByType('VERB')
            if first_verb:
                #there is at least one verb in the message
                #then the intent is on of CRUD operations (SAVE, DELETE, READ)
                #testing simmilarity for CRUD operations
                def setIntentIfSimilar(intent) -> bool:
                    if first_verb['word'] == intent:
                        self.intent = intent
                        return True
                    return False
                for i in Intent:
                    if setIntentIfSimilar(i):
                        break                                
            else:
                #there is no verb in the message
                #removing some candidate labels
                candidate_labels.remove(str(Intent.SAVE))
                #candidate_labels.remove(str(Intent.DELETE))
                candidate_labels.remove(str(Intent.READ))
                #seeking for direct commands without verb
                considered_tokens_count = len(self.tokens)
                considered_tokens_count -= len(self.getTokensByType('PUNCT'))
                if considered_tokens_count == 1:
                    #only one meaniful token in the message
                    #iterating over the candidate_labels for finding a direct command
                    for label in candidate_labels:
                        if Intent(label) == self.tokens[0]['word']:
                            self.intent = Intent(label)
                            break
                
            if self.intent is None:
                #no direct command found
                #find the intent
                intent_classifier = aie_obj.getPipeline("zero-shot-classification")
                self.intent_class_result = intent_classifier(considered_msg, candidate_labels=candidate_labels)
                self.intent = Intent(self.intent_class_result['labels'][0].upper())

            print(self.intent)

        def getFirstTokenByType(self, entityType):
            tokens = self.getTokensByType(entityType)
            if len(tokens)>0:
                return tokens[0]
            #else
            return None
        
        def getTokensByType(self, entityType) -> list:
            if entityType in self.tokens_bytype_map:
                return self.tokens_bytype_map[entityType]
            #else
            return []
        
        def getIntent(self) -> Intent:
            return self.intent

        def intentIs(self, intent) -> bool:
            return self.getIntent() == intent
            
        def intentIs_GREET(self) -> bool:
            return self.intentIs(Intent.GREETING)
        
        def intentIs_SAVE(self) -> bool:
            return self.intentIs(Intent.SAVE)

        def intentIs_DELETE(self) -> bool:
            return self.intentIs(Intent.DELETE)

        def intentIs_READ(self) -> bool:
            return self.intentIs(Intent.READ)

        def intentIs_SAY_GOODBYE(self) -> bool:
            return self.intentIs(Intent.GOODBYE)

        def intentIs_HELP(self) -> bool:
            return self.intentIs(Intent.HELP)

        def intentIs_CANCEL(self) -> bool:
            return self.intentIs(Intent.CANCELATION)

        def intentIs_CONFIRM(self) -> bool:
            return self.intentIs(Intent.CONFIRMATION)
        
    
    def __init__(self, AC):
        self.__AC = AC #Autonomous Controller Object
        self.__WIT_CLIENT = None
        self.__pipelines = {}
        
        #adding specialized pipelines/models
        self.__addToPipeline('text-similarity', SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2'))
        
        #initializing the simmilarity cache
        #key: alternative name of the entity (class or attribute)
        #value: string representation of the entity
        self.__similarityCache = {} 

    def getMsgParser(self, msg) -> __MsgParser:
        return self.__MsgParser(msg, self)

    #test if msg is a greeting
    def msgIsGoodbye(self, msg) -> bool:
        processedMsg = self.__getWitClient().message(msg) 
        parse = WITParser(processedMsg)       
        return parse.intentIs_SAY_GOODBYE()

    #test if msg is a greeting
    def msgIsGreeting(self, msg) -> bool:
        processedMsg = self.__getWitClient().message(msg) 
        parse = WITParser(processedMsg)       
        return parse.intentIs_GREET()

    #sentiment analysis
    def msgIsPositive(self, msg) -> bool:
        response = self.getPipeline('sentiment-analysis')(msg)
        #return True if positive or False if negative
        return response[0]['label'] == 'POSITIVE'

    def posTagMsg(self, msg):
        #configure the pipeline
        #pip = pipeline("token-classification", model = "vblagoje/bert-english-uncased-finetuned-pos")
        token_classifier = self.getPipeline("token-classification", model = "vblagoje/bert-english-uncased-finetuned-pos")

        #setting do_lower_case=False for all keys in the dictionary
        '''
        for config_key in token_classifier.tokenizer.pretrained_init_configuration.keys():
            token_classifier.tokenizer.pretrained_init_configuration[config_key]['do_lower_case'] = False
        token_classifier.tokenizer.do_lower_case = False
        token_classifier.tokenizer._decode_use_source_tokenizer = True
        token_classifier.tokenizer.init_kwargs['do_lower_case'] = False
        token_classifier.tokenizer.decoder.cleanup = False
        '''
        tokens = token_classifier(msg)
        return tokens
    
    def getAttributesFromMsg(self, msg, entity_class) -> list:
        attList = []
        tags = self.posTagMsg(msg)
        synonyms = self.__getSynonyms(entity_class)
        
        #finding the index after the entity class name in the message
        entity_class_token_idx = -1
        for i, token_i in enumerate(tags):
            #advance forward until the token of the entity class is found
            if token_i['word'] in synonyms:
                entity_class_token_idx = i                    
                break
        
        if entity_class_token_idx>-1: #if the entity class token was found
            question_answerer = self.getPipeline('question-answering')
            #iterate over the tokens and find the attribute names and values
            j = entity_class_token_idx + 1
            while j < len(tags):
                #advance foward until the token of the type "NOUN" is found (i.e. the first noun it is an attribute name)
                token_j = None
                while j < len(tags) and token_j is None:
                    if tags[j]['entity'] == 'NOUN':
                        token_j = tags[j]
                    else:
                        j += 1

                if token_j:
                    #found the first noun after token_j. It is the attribute name
                    attribute_name = token_j['word']        
                    #ask by the attribute value using question-answering pipeline
                    response = question_answerer(question='What is the ' + attribute_name + 
                                                 ' of the ' + entity_class + '?', context=msg)
                    #save the pair of attribute name and attribute value in the result list
                    attList.extend([attribute_name, response['answer']])
                    #update the j index to the next token after the attribute value
                    #get the end index in the original msg
                    att_value_idx_end = msg.find(response['answer'])
                    if att_value_idx_end > -1:
                        att_value_idx_end = att_value_idx_end + len(response['answer'])
                        while j < len(tags) and tags[j]['start'] < att_value_idx_end:
                            j += 1
                else:
                    #no noun found after token_j. It is the end of the attribute list
                    break
                
        return attList
    
    def getEntityClassFromMsg(self, msg, intent_name) -> str:
        question_answerer = self.getPipeline('question-answering')
        response = question_answerer(question="What is the entity class that the user command refers to?",
                                     context=self.__getEntityClassContext(msg, intent_name))
        if response['answer'] in self.__similarityCache.keys():
            return self.__similarityCache[response['answer']]
        #else
        if response['answer'] == intent_name:
            return None #it's an error. Probably the user did not informe the entity class in the right way.
        #else
        return response['answer']
    
    def __getEntityClassContext(self, msg, intent_name) -> str:
        context = "This is the user command: " + msg + ". "
        context += "\nThe intent of the user command is " + intent_name + ". "
        #adding the candidates
        candidates = []
        tags = self.posTagMsg(msg)
        attributes = self.__getAllAttributes()
        
        #get end index of the first VERB token in the message
        verb_intent_idx = -1
        #iterate over the tokens and find the first verb token
        for token in tags:
            verb_intent_idx += 1 
            if token['entity'] == 'VERB':
                break
        
        #iterate over the tags after the verb token (intent)
        for word in tags[verb_intent_idx+1:]:
            if (word['entity'] == 'NOUN' and #only nouns
                not(word['word'] in attributes) #not an knowed attribute
                ):
                candidates.append(word['word'])
                context += "\nPerhaps the entity class may be this: " + word['word'] + ". "
                break

        #adding current classes    
        break_loop = False
        for class_key in self.__AC.getEntitiesMap().keys():
            for candidate in candidates:
                if self.textsAreSimilar(class_key, candidate):
                    context = "The entity class is definitely this: " + class_key
                    break_loop = True
                    break
            if break_loop:
                break
                
        print(context)
        return context
    
    def __getAllAttributes(self) -> list:
        attList = []
        for class_key in self.__AC.getEntitiesMap().keys():
            for att_on_model in self.__AC.getEntitiesMap()[class_key].getAttributes():
                attList.append(att_on_model.name)
        return attList
    
    def addCustomSynonyms(self, key, word_list):
            for w in word_list:
                self.__similarityCache[w] = key
    
    def __getSynonyms(self, entity_name) -> list:
        synonyms = [entity_name]
        for alternative, original_name in self.__similarityCache.items():
            if entity_name == original_name:
                synonyms.append(alternative)
        return synonyms

    def textsAreSimilar(self, str1, str2, threshold=PNL_GENERAL_THRESHOLD) -> bool:
        #if the texts are equal, return True
        if str1 == str2:
            return True
        if str2 in self.__getSynonyms(str1) or str1 in self.__getSynonyms(str2):
            return True
        #else test similarity
        model = self.getPipeline("text-similarity")
        #Compute embedding for both texts
        embedding_1= model.encode(str1, convert_to_tensor=True)
        embedding_2 = model.encode(str2, convert_to_tensor=True)
        result = util.pytorch_cos_sim(embedding_1, embedding_2)[0][0].item()
        if result > threshold:
            self.__similarityCache[str2] = str1
            return True            
        #else            
        return False
    
    def __getWitClient(self):
        if self.__WIT_CLIENT == None:
            self.__WIT_CLIENT = Wit(access_token=WIT_ACCESS_KEY)
        return self.__WIT_CLIENT

    def getPipeline(self, pipeline_name, model=None, config=None):
        if pipeline_name not in self.__pipelines:
            self.__addToPipeline(pipeline_name, pipeline(pipeline_name, model=model, config=config))
        return self.__pipelines[pipeline_name]
    
    def __addToPipeline(self, pipeline_name, pipeline_object):
        self.__pipelines[pipeline_name] = pipeline_object
    
