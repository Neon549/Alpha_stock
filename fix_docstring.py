with open('tools/akshare_tools.py', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace(
    'def get_financial_indicator(symbol: str) -> str:\n',
    'def get_financial_indicator(symbol: str) -> str:\n    """获取A股财务指标数据，包括PE、PB、ROE等。"""\n'
)

with open('tools/akshare_tools.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('修复完成')