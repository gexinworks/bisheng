import json
from typing import Any, Dict, List, Optional

from bisheng_langchain.chains import LoaderOutputChain
from langchain.callbacks.manager import AsyncCallbackManagerForChainRun, CallbackManagerForChainRun
from langchain.chains.base import Chain
from pydantic import BaseModel, Extra

_TEXT_COLOR_MAPPING = {
    'blue': '36;1',
    'yellow': '33;1',
    'pink': '38;5;200',
    'green': '32;1',
    'red': '31;1',
}


def get_color_mapping(
    items: List[str], excluded_colors: Optional[List] = None
) -> Dict[str, str]:
    """Get mapping for items to a support color."""
    colors = list(_TEXT_COLOR_MAPPING.keys())
    if excluded_colors is not None:
        colors = [c for c in colors if c not in excluded_colors]
    color_mapping = {item: colors[i % len(colors)] for i, item in enumerate(items)}
    return color_mapping


class Output(BaseModel):
    """Output组件，用来控制输出"""

    @classmethod
    def initialize(cls, file_path: str = None):
        return file_path if file_path else ''


class Report(Chain):
    # ```
    # chain Dict:
    #    object: langchain_object
    #    node_id: object_key prefix
    #    input: triger query
    # variables Dict:
    #    variable_name: name
    #    variable_value: value
    # `
    chains: Optional[List[Dict]]
    variables: Optional[List[Dict]]
    report_name: str

    input_key: str = 'report_name'  #: :meta private:
    output_key: str = 'text'  #: :meta private:

    class Config:
        """Configuration for this pydantic object."""
        extra = Extra.forbid
        arbitrary_types_allowed = True

    @property
    def input_keys(self) -> List[str]:
        """Expect input key.
        :meta private:
        """
        return [self.input_key]

    @property
    def output_keys(self) -> List[str]:
        """Return output key.
        :meta private:
        """
        return [self.output_key]

    def validate_chains(cls, values: Dict) -> Dict:
        """Validate chains."""
        if values.get('chains'):
            for chain in values['chains']:
                chain_output_keys = chain['object'].output_keys
                if len(chain_output_keys) != 1:
                    raise ValueError(
                        'Chain used in Report should all have one output, got '
                        f"{chain['object']} with {len(chain_output_keys)} outputs."
                    )
            return values

    def func_call(self,
                  inputs: Dict[str, Any],
                  outputs: Dict[str, Any],
                  intermedia_stop: list,
                  chain: Chain,
                  node_id: str,
                  run_manager: Optional[CallbackManagerForChainRun] = None,):
        question = list(inputs.values())[0]
        _run_manager = run_manager or CallbackManagerForChainRun.get_noop_manager()

        if isinstance(chain, LoaderOutputChain):
            question = 'Get' + ','.join(question)
        _run_manager.on_text(text='', log='', type='start', category='question')
        _run_manager.on_text(text='', log=question, type='end', category='question')
        _run_manager.on_text(text='', log='', type='start', category='answer')
        message_reply = {'message': question, 'category': 'question'}
        intermedia_stop.append(message_reply)

        chain_outputs = chain(inputs, callbacks=_run_manager.get_child())
        result = (chain_outputs.get(chain.output_keys[0])
                  if isinstance(chain_outputs, dict) else chain_outputs)
        if isinstance(chain, LoaderOutputChain):
            schema = list(inputs.values())[0]
            result = json.loads(result)
            for key in schema:
                if result.get(key):
                    outputs.update({node_id+'_'+key:
                                    json.dumps(result.get(key), ensure_ascii=False)})
            result = json.dumps(result, ensure_ascii=False)
        else:
            outputs.update({node_id: result})
            message_reply = {'message': result, 'category': 'answer'}
            intermedia_stop.append(message_reply)
            _run_manager.on_text(text='', log=result, type='end', category='answer')

    async def func_acall(self,
                         inputs: Dict[str, Any],
                         outputs: Dict[str, Any],
                         intermedia_stop: list,
                         chain: Chain,
                         node_id: str,
                         run_manager: Optional[CallbackManagerForChainRun] = None,):
        question = list(inputs.values())[0]
        _run_manager = run_manager or CallbackManagerForChainRun.get_noop_manager()

        if isinstance(chain, LoaderOutputChain):
            question = 'Get' + ','.join(question)
        await _run_manager.on_text(text='', log='', type='start', category='question')
        await _run_manager.on_text(text='', log=question, type='end', category='question')
        await _run_manager.on_text(text='', log='', type='start', category='answer')
        message_reply = {'message': question, 'category': 'question'}
        intermedia_stop.append(message_reply)

        # process
        chain_outputs = await chain.arun(inputs, callbacks=_run_manager.get_child())
        result = (chain_outputs.get(chain.output_keys[0])
                  if isinstance(chain_outputs, dict) else chain_outputs)
        if isinstance(chain, LoaderOutputChain):
            schema = list(inputs.values())[0]
            result = json.loads(result)
            for key in schema:
                if result.get(key):
                    outputs.update({node_id+'_'+key:
                                    json.dumps(result.get(key), ensure_ascii=False)})
            result = json.dumps(result, ensure_ascii=False)
        else:
            outputs.update({node_id: result})
            message_reply = {'message': result, 'category': 'answer'}
            intermedia_stop.append(message_reply)
        await _run_manager.on_text(text='', log=result, type='end', category='answer')

    def _call(
        self,
        inputs: Dict[str, Any],
        run_manager: Optional[CallbackManagerForChainRun] = None,
        verbose: Optional[bool] = None,
    ) -> Dict[str, str]:
        intermedia_steps = []
        outputs = {}
        if self.chains:
            for i, chain in enumerate(self.chains):
                if not isinstance(chain['object'], Chain):
                    raise TypeError(
                        f"{chain['object']} not be runnable Chain object"
                    )
                if isinstance(chain['object'], LoaderOutputChain):
                    # loaderchain questions use new parse
                    self.func_call(chain['input'], outputs, intermedia_steps,
                                   chain['object'], chain['node_id'], run_manager)
                    continue

                preset_question = chain['input']
                for k, v in preset_question.items():
                    # log print
                    if isinstance(v, str):
                        self.func_call(preset_question, outputs, intermedia_steps,
                                       chain['object'], chain['node_id']+'_'+v, run_manager)
                    else:
                        for question in v:
                            question_dict = {k: question}
                            self.func_call(question_dict, outputs, intermedia_steps,
                                           chain['object'], chain['node_id']+'_'+question,
                                           run_manager)
        # variables
        if self.variables and self.variables[0]:
            for variable in self.variables:
                variable_kv = variable['input'][0]
                for k, v in variable_kv.items():
                    outputs.update({variable['node_id']+'_'+k: v})
        return {self.output_key: outputs, self.input_key: self.report_name,
                'intermediate_steps': intermedia_steps}

    async def _acall(
        self,
        inputs: Dict[str, Any],
        run_manager: Optional[AsyncCallbackManagerForChainRun] = None,
        verbose: Optional[bool] = None,
    ) -> Dict[str, Any]:
        intermedia_steps = []
        outputs = {}
        await run_manager.on_text(text='', log='', type='end', category='processing')  # end father start
        if self.chains:
            for i, chain in enumerate(self.chains):
                if not isinstance(chain['object'], Chain):
                    raise TypeError(
                        f"{chain['object']} not be runnable Chain object"
                    )
                if isinstance(chain['object'], LoaderOutputChain):
                    # loaderchain questions use new parse
                    await self.func_acall(chain['input'], outputs, intermedia_steps,
                                          chain['object'], chain['node_id'], run_manager)
                    continue
                # normal chain
                preset_question = chain['input']
                for k, v in preset_question.items():
                    if isinstance(v, str):
                        await self.func_acall(preset_question, outputs, intermedia_steps,
                                              chain['object'], chain['node_id']+'_'+v, run_manager)
                    else:
                        for question in v:
                            question_dict = {k: question}
                            await self.func_acall(question_dict, outputs, intermedia_steps,
                                                  chain['object'], chain['node_id']+'_'+question,
                                                  run_manager)
        # variables
        if self.variables and self.variables[0]:
            for variable in self.variables:
                variable_kv = variable['input'][0]
                for k, v in variable_kv.items():
                    outputs.update({variable['node_id']+'_'+k: v})

        # keep whole process paired
        await run_manager.on_text(text='', log='', type='start', category='processing')
        return {self.output_key: outputs, self.input_key: self.report_name,
                'intermediate_steps': intermedia_steps}
