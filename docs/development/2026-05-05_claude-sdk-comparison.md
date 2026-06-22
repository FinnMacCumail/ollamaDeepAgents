# Analysis: Claude SDK vs DeepAgents - What Can We Learn?

**Date:** 2026-05-05
**Purpose:** Compare Claude SDK implementation with DeepAgents to identify improvements

---

## Executive Summary

The Claude SDK app (`/home/ola/dev/netboxdev/claude-agentic-sdk/`) has several valuable patterns that could significantly improve the DeepAgents implementation:

**Key Findings:**
1. ✅ **More comprehensive system prompt** with field optimization patterns
2. ✅ **Better output formatting guidelines** (markdown tables, summaries)
3. ✅ **LangSmith integration** similar to our approach
4. ❌ **netbox-mcp-filters skill NOT being employed** in DeepAgents traces (evidence suggests)

---

## Comparison: System Prompts

### Claude SDK System Prompt (backend/agent.py:150-192)

**Strengths:**

#### 1. Field Optimization Rules
```
CRITICAL OPTIMIZATION RULES:
1. ALWAYS use the 'fields' parameter to minimize token usage (90% reduction possible)
2. NEVER request all fields unless explicitly asked for complete objects
3. Start with 'brief=true' for overview queries, then drill down with specific fields
4. Use 'netbox_search_objects' for global queries when object type is unknown
5. Use 'netbox_get_objects' when you know the specific object type
```

#### 2. Common Field Patterns
```
- Devices: fields=['id', 'name', 'status', 'device_type', 'site', 'primary_ip4']
- IP Addresses: fields=['id', 'address', 'status', 'dns_name', 'description', 'vrf']
- Sites: fields=['id', 'name', 'status', 'region', 'description', 'facility']
- Interfaces: fields=['id', 'name', 'type', 'enabled', 'device']
- VLANs: fields=['id', 'vid', 'name', 'status', 'site', 'description']
- Racks: fields=['id', 'name', 'site', 'status', 'u_height', 'facility_id']
- Circuits: fields=['id', 'cid', 'provider', 'type', 'status', 'description']
- Virtual Machines: fields=['id', 'name', 'status', 'cluster', 'vcpus', 'memory']
```

#### 3. Query Optimization Workflow
```
1. Analyze user question to determine required data
2. Select minimal field set that answers the question
3. Use pagination (limit/offset) for large datasets
4. Leverage ordering to get most relevant results first
5. For counting: use fields=['id'] only
```

#### 4. Output Formatting Guidelines
```
- Present results as concise markdown tables
- Highlight key information relevant to user's question
- Include summary statistics when appropriate
- For large result sets, show sample + summary (e.g., 'Showing 10 of 247 total')
- Always mention if results are paginated and how to get more
```

#### 5. Semantic Infrastructure Understanding
```
- Understand NetBox object relationships: Device → Site → Region
- Interface → Device, IP Address → Interface → Device
- VLAN → Site, Circuit → Provider
- Use two-step queries for cross-relationship filtering
- Remember: Multi-hop filters like 'device__site_id' are NOT supported
```

### DeepAgents System Prompt (src/agents/netbox_agent.py:20-48)

**Current Content:**
```
You are a NetBox infrastructure query assistant powered by DeepAgents.

CRITICAL CONSTRAINTS for NetBox MCP filters:
- NEVER use multi-hop filters with double underscores for relationships (e.g., device__site_id)
- NEVER use Django ORM lookups (e.g., __icontains, __in, __startswith)
- ALWAYS use two-step queries when filtering by related objects
- ALWAYS check the netbox-mcp-filters skill for filter guidance

When encountering filter errors:
1. Identify the problematic filter pattern
2. Break the query into multiple steps
3. Use netbox_search_objects for pattern matching

Query Patterns:
- Direct ID filters always work: {"device_id": 123}
- Exact name matches work: {"name": "exact-name"}
- For partial matches, use search

Remember to:
- Provide clear, concise responses
- Show relevant data fields
- Explain any workarounds used
- Suggest optimizations when applicable
```

**Strengths:**
- ✅ Clear filter constraints
- ✅ Two-step query guidance
- ✅ References skill system

**Missing:**
- ❌ Field optimization patterns
- ❌ Specific field examples per object type
- ❌ Output formatting guidelines
- ❌ Pagination strategies
- ❌ Semantic relationship mapping

---

## Evidence: Is netbox-mcp-filters Skill Being Used?

### Investigation

**Traces analyzed:**
- `019df45c-c873-7720-8dad-4fb15b8fc132` - "list all sites" (simple)
- `019df48b-26b3-7332-ab64-6758a3ebc275` - "list netbox sites" (simple)
- `019df7bd-ed28-78f0-91f9-7692f8ab13cb` - Rack elevation (complex)

**Findings:**

1. **No filter errors encountered** in any traced query
   - All queries were simple direct lookups
   - No relationship traversal attempted
   - Skills only load when needed (progressive disclosure)

2. **Skills configuration present:**
   ```python
   self.agent = create_deep_agent(
       model=model,
       tools=tools,
       system_prompt=NETBOX_SYSTEM_PROMPT,
       middleware=middleware,
       skills=self.skills_path,  # "src/skills"
   )
   ```

3. **System prompt references the skill:**
   ```
   - ALWAYS check the netbox-mcp-filters skill for filter guidance
   ```

4. **Trace data shows 90 runs** for rack elevation query
   - Includes `SkillsMiddleware.before_agent`
   - Includes `SkillsMiddleware.awrap_model_call`
   - Skills middleware is active

**Conclusion:**

🟡 **Inconclusive** - Skills are configured and middleware is active, but:
- No complex queries requiring the skill have been traced
- Need to test with a query that would trigger filter errors
- System prompt references the skill, suggesting it's available

**Test needed:**
```
"Show me all devices in the Akron site"
```
This should:
1. Attempt to use filters
2. Potentially hit filter constraints
3. Load the netbox-mcp-filters skill if needed
4. Apply two-step query pattern

---

## Comparison: Other Features

### LangSmith Integration

**Both implementations have LangSmith:**

**Claude SDK (backend/agent.py:114-139):**
```python
from langsmith.integrations.claude_agent_sdk import configure_claude_agent_sdk

if config.langchain_tracing_v2:
    os.environ["LANGCHAIN_API_KEY"] = config.langchain_api_key
    os.environ["LANGCHAIN_PROJECT"] = config.langchain_project
    configure_claude_agent_sdk()
```

**DeepAgents (.env):**
```bash
LANGCHAIN_API_KEY=lsv2_pt_xxxxxxxxxxxxxxxxxxxxxxxx_xxxxxxxxxx
LANGCHAIN_PROJECT=netbox-deepagents-llamacpp
LANGCHAIN_TRACING_V2=true
```

✅ Both implementations have LangSmith configured

### Anonymization

**Claude SDK has comprehensive anonymization:**
- `QueryAnonymizer` - Anonymize sensitive data in queries
- `ResponseRestorer` - Restore original values in responses
- `MappingService` - Manage anonymization mappings
- `HybridAnonymizer` - LLM + regex approach

**DeepAgents:**
- ❌ No anonymization layer

**Relevance:** Low priority for local deployment, but useful for:
- Sharing traces publicly
- Demo environments
- Multi-tenant scenarios

### Frontend

**Claude SDK:**
- ✅ Full Vue.js frontend with Nuxt
- ✅ Real-time streaming via WebSockets
- ✅ Conversation history
- ✅ Model selection UI
- ✅ Professional UX

**DeepAgents:**
- ❌ CLI only (`python -m src.main`)

**Relevance:** Frontend could improve usability, but:
- Adds complexity
- Not core to performance
- CLI is sufficient for development

---

## Recommendations

### Immediate: Enhance System Prompt

Add to `NETBOX_SYSTEM_PROMPT` in `src/agents/netbox_agent.py`:

```python
NETBOX_SYSTEM_PROMPT = """You are a NetBox infrastructure query assistant powered by DeepAgents.

Your role is to help users query and understand their NetBox infrastructure data efficiently.

## CRITICAL OPTIMIZATION RULES:
1. ALWAYS use the 'fields' parameter to minimize token usage (90% reduction possible)
2. NEVER request all fields unless explicitly asked for complete objects
3. Start with minimal fields for overview queries, then drill down with specific fields
4. Use 'netbox_search_objects' for global queries when object type is unknown
5. Use 'netbox_get_objects' when you know the specific object type

## COMMON FIELD PATTERNS:
- Devices: fields=['id', 'name', 'status', 'device_type', 'site', 'primary_ip4']
- IP Addresses: fields=['id', 'address', 'status', 'dns_name', 'description', 'vrf']
- Sites: fields=['id', 'name', 'status', 'region', 'description', 'facility']
- Interfaces: fields=['id', 'name', 'type', 'enabled', 'device']
- VLANs: fields=['id', 'vid', 'name', 'status', 'site', 'description']
- Racks: fields=['id', 'name', 'site', 'status', 'u_height', 'facility_id']
- Circuits: fields=['id', 'cid', 'provider', 'type', 'status', 'description']
- Virtual Machines: fields=['id', 'name', 'status', 'cluster', 'vcpus', 'memory']

## QUERY OPTIMIZATION WORKFLOW:
1. Analyze user question to determine required data
2. Select minimal field set that answers the question
3. Use pagination (limit/offset) for large datasets
4. Leverage ordering to get most relevant results first
5. For counting: use fields=['id'] only

## SEMANTIC INFRASTRUCTURE UNDERSTANDING:
- Understand NetBox object relationships: Device → Site → Region
- Interface → Device, IP Address → Interface → Device
- VLAN → Site, Circuit → Provider
- Rack → Site, Device → Rack
- Use two-step queries for cross-relationship filtering
- Remember: Multi-hop filters like 'device__site_id' are NOT supported

## OUTPUT FORMATTING:
- Present results as concise markdown tables
- Highlight key information relevant to user's question
- Include summary statistics when appropriate (e.g., "24 total sites")
- For large result sets, show sample + summary (e.g., "Showing 10 of 247 total")
- Always mention if results are paginated and how to get more
- For rack elevations, use ASCII visualization:
  ```
  U12 [  EMPTY  ]
  U11 [█] Device Name - Front
  U10 [█] Device Name - Front
  ```

## CRITICAL CONSTRAINTS for NetBox MCP filters:
- NEVER use multi-hop filters with double underscores (e.g., device__site_id)
- NEVER use Django ORM lookups (e.g., __icontains, __in, __startswith)
- ALWAYS use two-step queries when filtering by related objects
- ALWAYS check the netbox-mcp-filters skill for filter guidance

When encountering filter errors:
1. Identify the problematic filter pattern
2. Break the query into multiple steps:
   - First: Get the parent/related object by name or ID
   - Second: Use the object's ID in a simple filter
3. Use netbox_search_objects for pattern matching instead of complex filters

Query Patterns:
- Direct ID filters always work: {"device_id": 123}
- Exact name matches work: {"name": "exact-name"}
- For partial matches, use search: netbox_search_objects(query="pattern")
- For relationships, use two-step queries

Your goal: Provide accurate, efficient answers using minimal tokens while maintaining clarity and excellent formatting.
"""
```

**Expected Impact:**
- 🟢 Better field selection (reduce token usage by 50-90%)
- 🟢 Improved output formatting (tables, summaries, ASCII art)
- 🟢 More efficient queries (pagination, ordering)
- 🟢 Better rack elevation displays

### Medium-term: Test Skills System

**Test queries to verify skill loading:**

1. **Query requiring filter recovery:**
   ```
   "Show me all devices in the Akron site"
   ```
   - Should trigger two-step query pattern
   - May load netbox-mcp-filters skill

2. **Complex relationship query:**
   ```
   "List all IP addresses assigned to devices in New York"
   ```
   - Requires multi-step query
   - Tests skill application

3. **Search vs filter decision:**
   ```
   "Find all sites with 'DM' in the name"
   ```
   - Should use search instead of filters
   - Tests skill guidance

**Trace and analyze:**
- Check if skill is loaded
- Verify two-step pattern is applied
- Measure token savings from field optimization

### Long-term: Consider Frontend

**Only if needed for:**
- User-facing deployment
- Demo purposes
- Non-technical users

**Alternative:** Keep CLI-first approach with:
- Better formatting in terminal
- Interactive mode improvements
- Progress indicators

---

## Summary

### What to Borrow from Claude SDK

1. ✅ **Comprehensive system prompt** with:
   - Field optimization patterns
   - Common field examples
   - Output formatting guidelines
   - Semantic relationship mapping
   - Pagination strategies

2. ✅ **Query optimization workflow**
   - Minimal field selection
   - Pagination for large results
   - Summary statistics

3. ✅ **Output formatting standards**
   - Markdown tables
   - ASCII visualizations
   - Sample + summary pattern

4. 🟡 **Anonymization** (optional, lower priority)

5. ❌ **Frontend** (not needed for current use case)

### What DeepAgents Already Has

1. ✅ **Skills system** (more flexible than hardcoded prompts)
2. ✅ **LangSmith tracing**
3. ✅ **Filter recovery middleware**
4. ✅ **Metrics tracking**
5. ✅ **Local inference** (privacy + cost)

### Action Items

**Immediate (High Impact):**
1. Update system prompt with Claude SDK patterns
2. Add field optimization examples
3. Add output formatting guidelines
4. Add rack elevation templates

**Medium-term (Validation):**
1. Test with complex queries requiring skills
2. Verify skill loading in traces
3. Measure token savings from optimizations

**Long-term (Optional):**
1. Consider anonymization for shared traces
2. Evaluate frontend need

---

**Status:** ✅ Analysis Complete
**Next:** Update system prompt with Claude SDK improvements
**Expected Impact:** 50-90% token reduction, better formatting, improved UX
