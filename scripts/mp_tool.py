import datetime
import os
import sqlite3
import time
from typing import Dict, Optional

import click
import httpx

from bs4 import BeautifulSoup
import re


def format_content(content: str, content_format: str = "html"):
    # 格式化内容
    # content_format: 'text' or 'markdown' or 'html'
    # content: str
    # return: str
    try:
        if content_format == "text":
            # 去除HTML标签，保留纯文本
            soup = BeautifulSoup(content, "html.parser")
            text = soup.get_text().strip()
            content = re.sub(r"\n\s*\n", "\n", text)
        elif content_format == "markdown":
            # 去除span和font标签，只保留内容
            soup = BeautifulSoup(content, "html.parser")
            for tag in soup.find_all(class_="video_iframe"):
                tag.decompose()
            for tag in soup.find_all(["span", "font", "div", "strong", "b"]):
                # 如果style属性包含video_iframe，则删除整个tag
                tag.unwrap()
            for tag in soup.find_all(True):
                if "style" in tag.attrs:
                    del tag.attrs["style"]
                if "class" in tag.attrs:
                    del tag.attrs["class"]
                if "data-pm-slice" in tag.attrs:
                    del tag.attrs["data-pm-slice"]
                if "data-title" in tag.attrs:
                    # tag.append(tag.attrs['data-title'])
                    del tag.attrs["data-title"]

            content = str(soup)
            # 替换 p 标签中的换行符为空
            content = re.sub(
                r"(<p[^>]*>)([\s\S]*?)(<\/p>)",
                lambda m: m.group(1) + re.sub(r"\n", "", m.group(2)) + m.group(3),
                content,
            )
            content = re.sub(r"\n\s*\n\s*\n+", "\n", content)
            content = re.sub(r"\*", "", content)
            # print(content)
            from markdownify import markdownify as md

            # 处理图片标签，保留title属性
            soup = BeautifulSoup(content, "html.parser")
            for img in soup.find_all("img"):
                if "title" in img.attrs:
                    img["alt"] = img["title"]
            content = str(soup)
            # 转换HTML到Markdown
            content = md(
                content, heading_style="ATX", bullets="-*+", code_language="python"
            )
            content = re.sub(r"\n\s*\n\s*\n+", "\n\n", content)

    except Exception as e:
        click.echo("Error: format_content error: %s", e)
    return content

class MPScraper:
    """Base scraper with common HTTP functionality"""

    def __init__(self):
        self.token = os.environ.get("MPRSS_TOKEN")
        self.host = os.environ.get("MPRSS_HOST")
        self.timeout = float(os.environ.get("RSS_HTTP_TIMEOUT", "10"))
        self.max_retries = max(1, int(os.environ.get("RSS_HTTP_RETRIES", "2")))
        self.retry_backoff = float(os.environ.get("RSS_HTTP_BACKOFF", "0.8"))
        self.last_error = None
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Connection": "keep-alive",
            "Authorization": f"Bearer {self.token}",
        }

    def get(
        self,
        article_id: str,
        headers: Optional[Dict] = None,
        timeout: Optional[float] = None,
        retries: Optional[int] = None,
    ) -> httpx.Response:
        """Make GET request with retry logic"""
        url = f"http://{self.host}/rss/content/{article_id}"
        click.echo(url)
        request_timeout = timeout if timeout is not None else self.timeout
        max_retries = max(1, retries if retries is not None else self.max_retries)
        request_headers = {**self.headers, **(headers or {})}
        for attempt in range(max_retries):
            try:
                with httpx.Client(
                    timeout=request_timeout, follow_redirects=True
                ) as client:
                    response = client.get(url, headers=request_headers)
                    response.raise_for_status()
                    return response
            except Exception:
                if attempt == max_retries - 1:
                    raise
                time.sleep(self.retry_backoff * (attempt + 1))


def convert_timestamp(timestamp: int) -> str:
    """将时间戳转换为可读格式"""
    if timestamp:
        try:
            dt = datetime.fromtimestamp(timestamp)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return str(timestamp)
    return ""

def get_feeds_map(db_path: str):
    """获取feeds表的id到mp_name的映射"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT id, mp_name FROM feeds")
    feeds = {row[0]: row[1] for row in cursor.fetchall()}
    conn.close()
    return feeds

def article_to_markdown(article: str, output_dir: str, mp_name: str):
    """将单个文章转换为Markdown文件"""

    # 根据mp_id获取mp_name作为文件夹名
    # 创建以mp_name命名的子文件夹
    _article_output_path = os.path.join(output_dir, mp_name)
    os.makedirs(output_dir, exist_ok=True)

    # 处理content，将HTML转换为markdown
    markdown_content = format_content(article, content_format="markdown")

    if markdown_content:
        with open(f"{_article_output_path}.md","w",encoding="utf-8") as f:
            f.write(markdown_content)
    # 构建完整的markdown内容
    return markdown_content


@click.command(name="mp-tool", context_settings={"help_option_names": ["-h", "--help"]})
@click.option("--id",multiple=True,help="MP rss tool collections")
@click.option("--output-dir", help="The article save path",default="assets/articles")
@click.option("--stdout",is_flag=True, help="Wether output to stdout")
@click.pass_context
def mp_tool(ctx: click.Context,id, output_dir, stdout):
    """
    mp rss tool
    """
    os.environ["MPRSS_TOKEN"] = (
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhZG1pbiIsImV4cCI6MTc3MjM2MTY5MH0.Zx3noLAq3UbIhunAZgUxfIn_XCdWsVsRJgeq0GpyWFE"
    )
    os.environ["MPRSS_HOST"] = "45.207.211.49:8001"
    if not id:
        click.echo("Error：At least one --id parameter is required.", err=True)
        click.echo(ctx.get_help())
        return
    scraper = MPScraper()
    for item in id:
        resp = scraper.get(item)
        data = resp.read().decode("utf-8")
        md_content = article_to_markdown(data, output_dir,item)
        if stdout:
            click.echo(md_content)
    
if __name__ == "__main__":
    mp_tool()