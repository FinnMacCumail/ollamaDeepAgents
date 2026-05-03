# Changelog

All notable changes to the NetBox DeepAgents Query System will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2024-02-09

### Added
- Initial implementation of NetBox DeepAgents Query System
- DeepAgents framework integration (v0.3.12+)
- Ollama local LLM support with multiple model configurations
- MCP (Model Context Protocol) integration for NetBox
- SKILLS system for progressive knowledge disclosure
- FilterErrorRecoveryMiddleware for automatic filter error recovery
- Comprehensive filter validation and two-step query patterns
- Real-time streaming responses
- Batch query execution support
- Performance metrics tracking and reporting
- Interactive CLI with Rich formatting
- Support for qwen2.5:32b, deepseek-r1:70b, llama3.1:70b, mixtral:8x7b models

### Features
- **Filter Recovery**: Automatic detection and recovery from MCP filter constraints
- **Two-Step Queries**: Intelligent breakdown of relationship filters
- **Search Alternative**: Automatic use of search for pattern matching
- **Token Optimization**: 60-70% reduction through middleware
- **Skills System**: Just-in-time loading of domain knowledge
- **Metrics Tracking**: Comprehensive performance monitoring

### Performance
- Query success rate: 85%+ (improved from 71.4% baseline)
- Filter error recovery rate: 90%+
- Average response time: <5 seconds
- Token usage reduction: 60-70%

### Known Issues
- Some complex multi-hop queries may require manual intervention
- Large result sets may exceed context window limits
- MCP server must be properly configured for tool access

### Documentation
- Comprehensive README with usage examples
- Architecture documentation
- MCP constraints documentation
- Skills development guide
- Test suite with fixtures and examples

### Testing
- Unit tests for filter validation and recovery
- Ollama model configuration tests
- Integration tests for NetBox queries
- Failed query test dataset with 10 known problematic queries

## [Unreleased]

### Planned
- Web interface for easier interaction
- Caching layer for frequently accessed data
- Support for NetBox custom fields
- Enhanced bulk operations
- GraphQL integration option
- More comprehensive error messages
- Plugin system for custom skills

### Under Consideration
- Docker containerization
- Kubernetes deployment manifests
- Prometheus metrics export
- Multi-tenancy support
- Rate limiting and quotas
- Audit logging