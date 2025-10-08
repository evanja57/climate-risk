import os, json
from pathlib import Path
from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI
from typing import List

MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")


def _load_template(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def make_queries_chain():
    tmpl = open("prompts/generate_queries.txt", "r", encoding="utf-8").read()
    llm = ChatOpenAI(model=MODEL, temperature=1)
    def run(company_name: str) -> List[str]:
        rendered_prompt = tmpl.replace("[COMPANY_NAME]", company_name)
        resp = llm.invoke(rendered_prompt)
        txt = getattr(resp, "content", str(resp))
        
        # Clean the text of any problematic characters
        txt = txt.strip()
        
        # First, try JSON parsing
        try:
            # Try to extract JSON from the response if it's wrapped in markdown
            if "```json" in txt:
                start = txt.find("```json") + 7
                end = txt.find("```", start)
                if end > start:
                    txt = txt[start:end].strip()
            elif "```" in txt:
                start = txt.find("```") + 3
                end = txt.find("```", start)
                if end > start:
                    txt = txt[start:end].strip()
            
            # Try to parse as JSON
            arr = json.loads(txt)
            if isinstance(arr, list):
                # Filter out comments and clean queries
                clean_queries = []
                for item in arr:
                    query = str(item).strip('"')
                    # Skip comments (lines starting with //)
                    if not query.startswith('//') and len(query) > 10:
                        # Clean up malformed queries with trailing quotes and commas
                        query = query.rstrip('",').strip()
                        if query:
                            clean_queries.append(query)
                return clean_queries
        except Exception as e:
            print(f"Warning: JSON parsing failed ({e}), using fallback method")
            print(f"Raw response: {repr(txt[:200])}")
        
        # Fallback: search for JSON pattern in the output
        import re
        json_match = re.search(r'\[.*?\]', txt, re.DOTALL)
        if json_match:
            try:
                arr = json.loads(json_match.group())
                if isinstance(arr, list):
                    # Filter out comments and clean queries
                    clean_queries = []
                    for item in arr:
                        query = str(item).strip('"')
                        # Skip comments (lines starting with //)
                        if not query.startswith('//') and len(query) > 10:
                            # Clean up malformed queries with trailing quotes and commas
                            query = query.rstrip('",').strip()
                            if query:
                                clean_queries.append(query)
                    return clean_queries
            except Exception:
                pass
        
        # Last fallback: split by line and create natural queries
        lines = txt.split("\n")
        natural_queries = []
        
        for line in lines:
            line = line.strip("- • \"'").strip()
            # Skip empty lines, comments, and JSON brackets
            if (not line or 
                line.startswith('//') or 
                line.startswith('[') or 
                line.startswith(']') or 
                line.startswith('{') or 
                line.startswith('}') or
                len(line) < 10):
                continue
            
            # Clean up malformed queries
            line = line.rstrip('",').strip()
            
            # If line contains company name pattern, it's likely a query
            if company_name.lower() in line.lower() or '"' in line:
                # Remove extra quotes and clean up
                clean_line = line.strip('"').strip()
                if clean_line and len(clean_line) > 10:
                    natural_queries.append(clean_line)
        
        # If we still don't have good queries, generate some basic ones
        if len(natural_queries) < 5:
            basic_queries = [
                f"{company_name} company profile business overview",
                f"{company_name} ESG sustainability report",
                f"{company_name} environmental impact carbon emissions",
                f"{company_name} social responsibility initiatives",
                f"{company_name} governance board leadership",
                f"{company_name} controversies scandals news",
                f"{company_name} financial performance revenue",
                f"{company_name} supply chain sustainability",
                f"{company_name} employee diversity inclusion",
                f"{company_name} regulatory compliance violations"
            ]
            natural_queries.extend(basic_queries)
        
        return natural_queries[:50]  # Limit to 50 queries max
    return run

def make_report_chain():
    tmpl = open("prompts/esg_report.txt", "r", encoding="utf-8").read()
    prompt = PromptTemplate.from_template(tmpl)
    llm = ChatOpenAI(model=MODEL, temperature=0)
    def run(company_name, evidence):
        try:
            # Replace placeholders directly in the template string
            safe_company_name = company_name.replace('"', '\\"')
            final_prompt = prompt.template.replace("[COMPANY_NAME]", safe_company_name)
            final_prompt = final_prompt.replace("[EVIDENCE]", evidence)
            
            # Invoke the model directly with the final prompt string
            resp = llm.invoke(final_prompt)
            content = getattr(resp, "content", str(resp))
            
            # Validate content
            if not content or content.strip() == "":
                return "Error: Empty response from AI model"
            
            return content
            
        except Exception as e:
            return f"Error generating report: {str(e)}"
    return run



def make_scenario_chain():
    template_text = _load_template("prompts/transition_scenarios.txt")
    llm = ChatOpenAI(model=MODEL, temperature=1)

    def run(company_name: str, evidence: str) -> str:
        safe_company = company_name.replace('"', '\\"')
        prompt_text = (
            template_text
            .replace("[COMPANY_NAME]", safe_company)
            .replace("[SCENARIO_EVIDENCE]", evidence or "Information not provided.")
        )
        resp = llm.invoke(prompt_text)
        content = getattr(resp, "content", str(resp))
        if not content or not content.strip():
            return "Error: Empty response from AI model"
        return content

    return run
