from requests import session
from utils import thread_pool
import pandas as pd
from datetime import datetime

class sfera_tasks:
    auth_cread: dict
    session: session
    server: str
    api_dict: dict
    n_threads:int=10

    def __init__(self, server: str, username: str, password: str) -> None:
        self.auth_cread = {"username": username, "password": password}
        self.server = server
        self.api_dict = {'auth': '/api/auth/login',
                         'sprints': '/app/tasks/api/v0.1/sprints',
                         'task_info': '/app/tasks/api/v0.1/entities/{task_key}',
                         'tasks_to_project': '/app/tasks/api/v0.1/entities?areaCode={project_key}',
                         'task':'/app/tasks/api/v0.1/entities',
                         'statuses':'/app/tasks/api/v0.1/dictionaries/entity-statuses'}

    def __url(self, api_key):
        return f'{self.server}{self.api_dict[api_key]}'

    def _init_session(self) -> session:
        self.session = session()
        r = self.session.post(self.__url(
            'auth'), json=self.auth_cread, verify=False)
        return r.ok

    def __get_pages(self, worker,params:dict) -> list:
        response=worker(params)
        res=response['content']
        n_pages=response['totalPages']
        if n_pages>1:
            r_list=thread_pool(worker,({**params,**{'page':str(i)}} for i in range(n_pages)),self.n_threads)
            res=[]
            for el  in r_list:
                res+=[*el['content']]
        return res

    def sprint(self) -> dict:
        _worker=lambda params:self.session.get(self.__url('sprints'), params=params,headers={"authorization": None},verify=False).json()
        params={"size": "1000"}
        res=self.__get_pages(_worker,params)
        return res

    def task_info(self, task_key: str) -> dict:
        res = self.session.get(self.__url('task_info').format(
            task_key=task_key), headers={"authorization": None},verify=False)
        return res.json()
    
    def _query_project_tasks(self,project_key:str,query:str,full_info=False)->list:
        _worker=lambda params:self.session.get(self.__url('tasks_to_project').format(project_key=project_key), params=params,headers={"authorization": None}).json()
        params={"query": query, "size": "1000"}
        res=self.__get_pages(_worker,params) 
        if full_info:
            res= thread_pool(self.task_info,(_task['number'] for _task in res),self.n_threads)     
        return res
    
    def get_sprint_tasks(self, sprint_id: int,project_key:str,full_info=False) -> list:
        query= f"(sprint = {sprint_id})"
        res=self._query_project_tasks (project_key,query,full_info)
        return res
    
    def create_task(self,task_params:dict):
        res=self.session.post(self.__url('task'),json=task_params,
                              headers={"authorization": None},verify=False)
        return res
    
    def update_task(self,task_key:str,task_params:dict):
        res=self.session.patch(self.__url('task_info').format(task_key=task_key),json=task_params,
                              headers={"authorization": None},verify=False)
        return res
    
    def get_status_info(self)->list:
        res = self.session.get(self.__url('statuses'), headers={"authorization": None},verify=False)
        return res.json()        

class sfera_reports(sfera_tasks):
    sprints: dict
    colors:dict={'danger':' #ffe6e6','warn':'#EFEEB4','ok':'#e6ffe6'}
    _thread_pool=thread_pool
    status_dict:list
    def __init__(self,**kwargs):
        sfera_tasks.__init__(self,**kwargs)
        print(f'session opened: {self._init_session()}')
        self.sprints=self.sprint()
        self.status_dict={el['code']:{k:v for k,v in el.items() if k!='code'}  for el in self.get_status_info()}
    
    def get_backlog(self,project_key:str,full_info:bool=True):
        query="(statusCategory != 'Done') and (state = 'Normal') and not (hasActiveSprint() or hasPlannedSprint())"
        res=self._query_project_tasks (project_key,query,full_info)
        return res
    def create_task_data(self,summary:str,
                         priority:str='average',
                         status:str='created',
                         task_type:str='task',
                         description:str='',
                         assignee_email:str='',
                         owner_email:str='',
                         duedate:str='',
                         estimation_sec:int='',
                         parent_issue:str='',
                         project_code:str='',
                         sprint_id:int=None,
                         streamConsumer:str='',
                         streamOwner:str='',
                         projectconsumer_code:str='',
                         issue_type:str='Новая функциональность',
                         changeType:str='Создание/Доработка ИС',
                         systems:str='',
                         acceptanceCriteria:str='',
                         decision:str=''
                         )->dict:
        
        customFieldsValues=[{"code":"streamConsumer","value":streamConsumer},
                                   {"code":"streamOwner","value":streamOwner},
                                   {"code":"projectConsumer",
                                    "value":projectconsumer_code},#156
                                   {"code":"workGroup","value":issue_type},#"Архитектурная задача"}
                                   {"code":"changeType","value":changeType},
                                   {"code":"systems","value":systems},#1415
                                   {"code":"decision","value":decision},
                                   {"code":"rightTransferApproval","value":True},
                                   {"code":"acceptanceCriteria", "value":acceptanceCriteria}]
        
        if task_type=='task':
            customFieldsValues=[el for el in customFieldsValues if el['code'] not in ("changeType","decision",'rightTransferApproval','acceptanceCriteria')]

        data={"name":summary,
              "priority":priority,
              "status":status,
             "type":task_type,
             "description":description,
             "assignee":assignee_email,
             "owner":owner_email,
             "dueDate":duedate,
             "estimation":estimation_sec,
             "parent":parent_issue,
             "areaCode":project_code,
             "sprint":sprint_id,
             "customFieldsValues":customFieldsValues}
        return data
    
    def get_sprint_id_by_name(self,name:str)->int:
        res=[_row['id'] for _row in self.sprints if name in _row['name']]

        assert len(res) == 1 , 'Должен находиться 1 спринт по маске'
        return res[0]
    
    def _get_sprint(self,task):
        sprint=task.get('actualSprint',None)
        if sprint is None:
            sprint=task.get('closedSprints',None)[0]
        res={'name':None,'startDate':None,'endDate':None,}
        if sprint is not None:
        
            for key  in ('name','startDate','endDate'):
                res[key]=sprint[key]
        return res
    def parse_task(self,task)->dict:
        _filter=('number','name','description','type','status','dueDate','estimation','priority','createDate','state','directLink')
        res={k:v for k,v in task.items() if k in _filter}
        
        fio=lambda d: '' if d is None else f"{d['lastName']} {d['firstName']} {d['patronymic']}"
        res['assignee']=fio(task.get('assignee',None))
        res['assignee_email']=task.get('assignee',{'email':None})['email']
        res['owner']=fio(task.get('owner',None))
        res['owner_email']=task.get('owner',{'email':None})['email']
        custom_fields={t['code']:{k:v for k,v in t.items() if k!='code'} for t in task['customFieldsValues']}
        res['task_type']=custom_fields.get ('workGroup',{'value':None})['value']
        
        res['status']=task['status']
        res['status_category']=self.status_dict[task['status']]['categoryCode']
        res['parent']=task.get('parent',None)
        res['label']=task.get('label',None)
        sprint=self._get_sprint(task)
        for key  in ('name','startDate','endDate'):
            res[f"sprint_{key}"]=sprint[key]    
        return {**res,**{ k:v['value'] for k,v in custom_fields.items()}}    
    
    def calc_metrics(self,tasks)->tuple:
        _df=pd.DataFrame([self.parse_task(task) for task in tasks])
        
        _df['estimation_day']=_df['estimation']/3600/8
        df=_df.copy(deep=True)
        df.fillna({_col:'None' for _col in df.columns if _col not in ('estimation_day')},inplace=True)
        metrics={}
        metrics['max_task_estimation']={'descr':'Длительность одной задачи не должна превышать 3х дней','data':df.agg({"estimation_day": [min,max]})}
        metrics['total_estimation']={'descr':'Плановое ч/д на спринт =9 (за исключением больничных/ отпусков/ переработок)','data':df.pivot_table(values='estimation_day',index=['assignee'],aggfunc='sum',margins=True).reset_index()}
        task_type_dist=df.pivot_table(values='estimation_day',index=['task_type'],aggfunc='sum',margins=True).reset_index()
        task_type_dist['% of total']=(task_type_dist['estimation_day']/(task_type_dist['estimation_day'].sum()/2)).apply(lambda x:'{:.2%}'.format(x))
        
        metrics['task_type_dist']={'descr':'Тех долг должен занимать не менее 20%','data':task_type_dist}
        sprint_dates=[datetime.strptime(_date[:10],'%Y-%m-%d') for _date in df[['sprint_startDate','sprint_endDate']].iloc[0].to_list()]
        min_max_duedates=df[df['dueDate']!='None']['dueDate'].apply(lambda s:datetime.strptime(s,'%Y-%m-%d') ).agg([min,max]).to_list()
        min_max_duedate=pd.DataFrame([sprint_dates,min_max_duedates],columns=['min','max'],index=['Начало/окончание спринта','duedate'])
        null_duedate=pd.DataFrame([df[df['dueDate']=='None']['dueDate'].count()],index=['Незаполненный duedate'],columns=['count'])
        
        metrics['min_max_duedates']={'descr':'Срок исполнения не должен превышать конец спринта и должен  >= начало спринта +1 день','data':min_max_duedate.T}
        metrics['null_duedate']={'descr':'Число незаполненных Сроков исполнения','data':null_duedate}
 
        agg_func=lambda s:df.fillna('None').pivot_table(values='number',index=[s],aggfunc='count',margins=True).reset_index()
        
        type_consumer=df.pivot_table(values='number',index=['task_type','projectConsumer'],aggfunc='count',margins=True)
        
        for _m in ('streamConsumer','projectConsumer','systems', 'streamOwner','systemsCode'):
            metrics[_m]={'descr':f'Число задач в разрезе {_m}','data':agg_func(_m)}
        metrics['type_consumer']={'descr':'Проект и тип задачи коррелирует между собой 1565 - Тех долг, 1503 -Новый функционал','data':type_consumer}
        
        return _df,metrics
    
    def __highlight_row(self,_df_,f):  
        return _df_.style.apply(lambda s:[f'background-color: {f(s)}'] * len(s), axis=1)
    
    def color_metrics(self,metrics:dict)->dict:
        metrics['max_task_estimation']['data']=metrics['max_task_estimation']['data'].style.map(lambda x:f'background-color: {self.colors["danger"]};' if x>3 else None)
        metrics['total_estimation']['data']=self.__highlight_row(metrics['total_estimation']['data'],
                                                                 lambda x: self.colors["danger"] if  x["assignee"]=='None' else (self.colors["warn"] if x['estimation_day']!=9 and x['assignee']!='All' else None))
        
        metrics['task_type_dist']['data']=self.__highlight_row(metrics['task_type_dist']['data'],
                                                                 lambda x: self.colors["danger"] if  x["task_type"]=='None' or (x["task_type"]=='Технический долг' and float(x["% of total"][:-1])<20 )  else (self.colors["ok"] if x["task_type"]=='Технический долг' and float(x["% of total"][:-1])>=20  else None))
        
        def __min_max_duedates_color(x):
            if x.name=='max':
                if x['duedate']!=x['Начало/окончание спринта']:
                    _color=self.colors["danger"] 
                else:
                    _color=self.colors["ok"] 
            else:
               if (x['duedate']-x['Начало/окончание спринта']).days>=1:
                    _color=self.colors["ok"]
               else:
                   _color=self.colors["danger"] 
            return _color
        metrics['min_max_duedates']['data']=self.__highlight_row(metrics['min_max_duedates']['data'],__min_max_duedates_color)
        metrics['null_duedate']['data']=self.__highlight_row(metrics['null_duedate']['data'],
                                                                 lambda x: self.colors["danger"] if  x["count"]>0   else self.colors["ok"])
         
        metrics['streamConsumer']['data']=self.__highlight_row(metrics['streamConsumer']['data'],lambda x: self.colors["danger"] if  x['streamConsumer']=='None'  else None)      
        metrics['projectConsumer']['data']=self.__highlight_row(metrics['projectConsumer']['data'],lambda x: self.colors["danger"] if  x['projectConsumer']=='None'  else None)      
        metrics['systems']['data']=self.__highlight_row(metrics['systems']['data'],lambda x: self.colors["danger"] if  x['systems']=='None'  else None)      
        metrics['streamOwner']['data']=self.__highlight_row(metrics['streamOwner']['data'],lambda x: self.colors["danger"] if  x['streamOwner']=='None'  else None)      
        metrics['systemsCode']['data']=self.__highlight_row(metrics['systemsCode']['data'],lambda x: self.colors["danger"] if  x['systemsCode']=='None'  else None)      
          
        return metrics
    
    

        