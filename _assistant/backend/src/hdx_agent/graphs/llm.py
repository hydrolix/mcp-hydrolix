from langchain_core.messages import HumanMessage
from langchain_core.messages.utils import count_tokens_approximately
from langchain_openai import AzureChatOpenAI, ChatOpenAI, OpenAIEmbeddings
from langchain_openai.chat_models.base import BaseChatOpenAI
from langmem.short_term import SummarizationNode

from hdx_agent.config import Config


def _create_graph_model(cnf: dict) -> BaseChatOpenAI:
    """Creates langchain model by type and other properties provided."""
    mapping = {}
    cls = None
    if cnf.api_type == "litellm":
        cls = ChatOpenAI
        mapping = {
            "base_url": "api_base_url",
            "api_key": "api_key",
            "model": "model_name",
            "timeout": "timeout",
            "temperature": "temperature",
            "top_p": "top_p",
            "max_tokens": "max_tokens",
            "max_completion_tokens": "max_completion_tokens",
        }
    elif cnf.api_type == "azure":
        cls = AzureChatOpenAI
        mapping = {
            "azure_endpoint": "api_base_url",
            "api_key": "api_key",
            "api_version": "api_version",
            "deployment_name": "model_name",
            "model_name": "model_name",
            "timeout": "timeout",
            "temperature": "temperature",
            "top_p": "top_p",
            "max_tokens": "max_tokens",
            "max_completion_tokens": "max_completion_tokens",
        }

    return cls(**{k: cnf[v] for k, v in mapping.items() if v in cnf})


def create_graph_models(config: Config) -> tuple[BaseChatOpenAI, BaseChatOpenAI, SummarizationNode, OpenAIEmbeddings]:
    """Creates models provided in application config."""

    graph_config = config.graph
    assistant_model = _create_graph_model(graph_config.assistant)
    summary_model = _create_graph_model(graph_config.summary)

    token_counter = count_tokens_approximately
    try:
        summary_model.get_num_tokens_from_messages(messages=[HumanMessage(content="number of tokens here")])
        token_counter = summary_model.get_num_tokens_from_messages
    except NotImplementedError:
        pass
    cnf = graph_config.summary
    summarization_node = SummarizationNode(
        model=summary_model,
        token_counter=token_counter,
        max_tokens=cnf.get("max_completion_tokens") or cnf.max_tokens,
        max_tokens_before_summary=cnf.max_tokens_before_summary,
        max_summary_tokens=cnf.max_summary_tokens,
    )

    embeddings = OpenAIEmbeddings(
        model=graph_config.embedding.model_name,
        api_key=graph_config.embedding.api_key,
        base_url=graph_config.embedding.api_base_url,
        timeout=graph_config.embedding.timeout,
    )
    return assistant_model, summary_model, summarization_node, embeddings
