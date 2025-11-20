import json
import os
import requests
from urllib.parse import urlparse, parse_qs, unquote
from loguru import logger
from apis.xhs_pc_apis import XHS_Apis
from xhs_utils.common_util import init
from xhs_utils.data_util import handle_note_info, download_note, save_to_xlsx


class Data_Spider():
    def __init__(self):
        self.xhs_apis = XHS_Apis()

    def spider_note(self, note_url: str, cookies_str: str, proxies=None):
        """
        爬取一个笔记的信息
        :param note_url:
        :param cookies_str:
        :return:
        """
        note_info = None
        try:
            success, msg, note_info = self.xhs_apis.get_note_info(note_url, cookies_str, proxies)
            if success:
                note_info = note_info['data']['items'][0]
                note_info['url'] = note_url
                note_info = handle_note_info(note_info)
        except Exception as e:
            success = False
            msg = e
        logger.info(f'爬取笔记信息 {note_url}: {success}, msg: {msg}')
        return success, msg, note_info

    def spider_user_from_note_url(self, note_url: str, cookies_str: str, base_path: dict, save_choice: str, excel_name: str = '', proxies=None):
        """
        从笔记链接中提取用户信息，然后爬取该用户的所有笔记
        :param note_url: 笔记链接
        :param cookies_str: Cookie字符串
        :param base_path: 保存路径
        :param save_choice: 保存选择
        :param excel_name: Excel文件名
        :param proxies: 代理
        :return:
        """
        try:
            logger.info(f"正在从笔记链接提取用户信息: {note_url}")
            
            # 先爬取这个笔记获取用户信息
            success, msg, note_info = self.spider_note(note_url, cookies_str, proxies)
            if not success or not note_info:
                logger.error(f"无法获取笔记信息: {msg}")
                return [], False, msg
            
            # 从笔记信息中提取用户ID和用户名
            user_id = note_info.get('user_id') or ""
            user_name = note_info.get('nickname') or "未知用户"
            
            if not user_id:
                logger.error("笔记信息中未找到用户ID")
                logger.error(f"笔记信息字段: {list(note_info.keys())}")
                return [], False, "未找到用户ID"
            
            logger.info(f"找到用户: {user_name} (用户ID: {user_id})")
            
            # 如果没有提供excel_name，使用用户名
            if not excel_name:
                excel_name = user_name
            
            # 尝试获取该用户的所有笔记
            user_url = f"https://www.xiaohongshu.com/user/profile/{user_id}"
            logger.info(f"尝试爬取用户所有笔记: {user_url}")
            note_list, success, msg = self.spider_user_all_note(user_url, cookies_str, base_path, save_choice, excel_name, proxies)
            
            if not success:
                logger.warning(f"直接获取用户笔记失败: {msg}，尝试通过搜索获取")
                # 如果直接获取失败，尝试通过搜索获取
                note_list, success, msg = self.spider_user_by_red_id("", user_name, cookies_str, base_path, save_choice, excel_name, proxies)
            
            return note_list, success, msg
            
        except Exception as e:
            logger.error(f"从笔记链接提取用户信息时出错: {e}")
            return [], False, str(e)

    def spider_some_note(self, notes: list, cookies_str: str, base_path: dict, save_choice: str, excel_name: str = '', proxies=None):
        """
        爬取一些笔记的信息
        :param notes:
        :param cookies_str:
        :param base_path:
        :return:
        """
        if (save_choice == 'all' or save_choice == 'excel') and excel_name == '':
            raise ValueError('excel_name 不能为空')
        note_list = []
        for note_url in notes:
            success, msg, note_info = self.spider_note(note_url, cookies_str, proxies)
            if note_info is not None and success:
                note_list.append(note_info)
        for note_info in note_list:
            if save_choice == 'all' or 'media' in save_choice:
                download_note(note_info, base_path['media'], save_choice)
        if save_choice == 'all' or save_choice == 'excel':
            file_path = os.path.abspath(os.path.join(base_path['excel'], f'{excel_name}.xlsx'))
            save_to_xlsx(note_list, file_path)


    def spider_user_all_note(self, user_url: str, cookies_str: str, base_path: dict, save_choice: str, excel_name: str = '', proxies=None):
        """
        爬取一个用户的所有笔记
        :param user_url:
        :param cookies_str:
        :param base_path:
        :return:
        """
        note_list = []
        try:
            success, msg, all_note_info = self.xhs_apis.get_user_all_notes(user_url, cookies_str, proxies)
            if success:
                logger.info(f'用户 {user_url} 作品数量: {len(all_note_info)}')
                for simple_note_info in all_note_info:
                    note_url = f"https://www.xiaohongshu.com/explore/{simple_note_info['note_id']}?xsec_token={simple_note_info['xsec_token']}"
                    note_list.append(note_url)
            if save_choice == 'all' or save_choice == 'excel':
                excel_name = user_url.split('/')[-1].split('?')[0]
            self.spider_some_note(note_list, cookies_str, base_path, save_choice, excel_name, proxies)
        except Exception as e:
            success = False
            msg = e
        logger.info(f'爬取用户所有视频 {user_url}: {success}, msg: {msg}')
        return note_list, success, msg

    def spider_user_by_red_id(self, red_id: str, user_name: str, cookies_str: str, base_path: dict, save_choice: str, excel_name: str = '', proxies=None):
        """
        通过小红书号搜索用户并爬取笔记
        :param red_id: 小红书号
        :param user_name: 用户名称
        :param cookies_str:
        :param base_path:
        :param save_choice:
        :param excel_name:
        :param proxies:
        :return:
        """
        note_list = []
        try:
            # 先搜索用户获取用户ID
            logger.info(f"正在搜索用户: {user_name} (小红书号: {red_id})")
            success, msg, search_result = self.xhs_apis.search_user(red_id, cookies_str, 1, proxies)
            
            # 添加调试日志查看搜索结果
            if success and search_result:
                logger.debug(f"搜索结果: {json.dumps(search_result, ensure_ascii=False)[:500]}")
            
            if not success:
                logger.warning(f"搜索用户失败: {msg}，尝试直接搜索笔记")
                # 如果搜索用户失败，直接通过小红书号搜索笔记
                success, msg, notes = self.xhs_apis.search_some_note(red_id, 100, cookies_str, 0, 0, 0, 0, 0, "", proxies)
                if success:
                    for note in notes:
                        if note.get('model_type') == 'note':
                            # 筛选出该用户的笔记（通过检查用户信息）
                            note_url = f"https://www.xiaohongshu.com/explore/{note['id']}?xsec_token={note.get('xsec_token', '')}"
                            note_list.append(note_url)
            else:
                # 找到用户，获取用户ID
                users = search_result.get("data", {}).get("users", [])
                target_user = None
                for user in users:
                    user_red_id = user.get("red_id") or user.get("redId") or ""
                    user_nickname = user.get("nickname") or user.get("name") or ""
                    if user_red_id == red_id or red_id in user_nickname or user_name in user_nickname:
                        target_user = user
                        break
                
                if target_user:
                    # 尝试多个可能的字段名
                    user_id = target_user.get("user_id") or target_user.get("userId") or target_user.get("id") or ""
                    if not user_id:
                        # 如果没有user_id，尝试从其他字段提取
                        logger.warning(f"未找到用户ID字段，用户信息: {target_user}")
                    logger.info(f"找到用户 {user_name}，用户ID: {user_id}")
                    
                    # 如果找到有效的用户ID，尝试直接获取笔记
                    if user_id:
                        user_url = f"https://www.xiaohongshu.com/user/profile/{user_id}"
                        success, msg, all_note_info = self.xhs_apis.get_user_all_notes(user_url, cookies_str, proxies)
                        if success and all_note_info:
                            logger.info(f'用户 {user_name} 作品数量: {len(all_note_info)}')
                            for simple_note_info in all_note_info:
                                note_url = f"https://www.xiaohongshu.com/explore/{simple_note_info['note_id']}?xsec_token={simple_note_info.get('xsec_token', '')}"
                                note_list.append(note_url)
                    
                    # 如果直接获取失败或没有用户ID，通过搜索笔记获取
                    if not note_list:
                        logger.info(f"尝试通过搜索笔记获取用户 {user_name} 的笔记")
                        # 尝试搜索用户名和小红书号
                        search_queries = [user_name, red_id]
                        found_user_ids = set()
                        
                        # 先从搜索结果中收集可能的用户ID
                        if target_user:
                            found_user_ids.add(user_id)
                            # 尝试其他可能的ID字段
                            for key in target_user.keys():
                                if 'id' in key.lower() and target_user[key]:
                                    found_user_ids.add(str(target_user[key]))
                        
                        # 通过搜索笔记来获取
                        for query in search_queries:
                            if not query:
                                continue
                            logger.info(f"搜索笔记关键词: {query}")
                            success, msg, notes = self.xhs_apis.search_some_note(query, 200, cookies_str, 0, 0, 0, 0, 0, "", proxies)
                            if success:
                                for note in notes:
                                    if note.get('model_type') == 'note':
                                        note_user = note.get('user', {})
                                        note_user_id = note_user.get('user_id') or note_user.get('userId') or note_user.get('id') or ""
                                        note_user_name = note_user.get('nickname') or note_user.get('name') or ""
                                        
                                        # 匹配用户：用户ID匹配或用户名匹配
                                        if (user_id and note_user_id == user_id) or \
                                           user_name in note_user_name or \
                                           (user_id in found_user_ids and note_user_id in found_user_ids) or \
                                           (not note_list and red_id in note_user.get('red_id', '')):
                                            note_url = f"https://www.xiaohongshu.com/explore/{note['id']}?xsec_token={note.get('xsec_token', '')}"
                                            if note_url not in note_list:
                                                note_list.append(note_url)
                                
                                if note_list:
                                    logger.info(f"通过搜索找到 {len(note_list)} 条笔记")
                                    break
                else:
                    logger.warning(f"未找到用户 {user_name} (小红书号: {red_id})，尝试直接搜索笔记")
                    # 通过用户名搜索笔记
                    success, msg, notes = self.xhs_apis.search_some_note(user_name, 200, cookies_str, 0, 0, 0, 0, 0, "", proxies)
                    if success:
                        for note in notes:
                            if note.get('model_type') == 'note':
                                note_url = f"https://www.xiaohongshu.com/explore/{note['id']}?xsec_token={note.get('xsec_token', '')}"
                                note_list.append(note_url)
            
            if note_list:
                logger.info(f"找到 {len(note_list)} 条笔记，开始爬取...")
                if save_choice == 'all' or save_choice == 'excel':
                    if not excel_name:
                        excel_name = user_name
                self.spider_some_note(note_list, cookies_str, base_path, save_choice, excel_name, proxies)
                return note_list, True, "成功"
            else:
                return [], False, "未找到笔记"
                
        except Exception as e:
            logger.error(f"爬取用户 {user_name} 时出错: {e}")
            return [], False, str(e)

    def spider_some_search_note(self, query: str, require_num: int, cookies_str: str, base_path: dict, save_choice: str, sort_type_choice=0, note_type=0, note_time=0, note_range=0, pos_distance=0, geo: dict = None,  excel_name: str = '', proxies=None):
        """
            指定数量搜索笔记，设置排序方式和笔记类型和笔记数量
            :param query 搜索的关键词
            :param require_num 搜索的数量
            :param cookies_str 你的cookies
            :param base_path 保存路径
            :param sort_type_choice 排序方式 0 综合排序, 1 最新, 2 最多点赞, 3 最多评论, 4 最多收藏
            :param note_type 笔记类型 0 不限, 1 视频笔记, 2 普通笔记
            :param note_time 笔记时间 0 不限, 1 一天内, 2 一周内天, 3 半年内
            :param note_range 笔记范围 0 不限, 1 已看过, 2 未看过, 3 已关注
            :param pos_distance 位置距离 0 不限, 1 同城, 2 附近 指定这个必须要指定 geo
            返回搜索的结果
        """
        note_list = []
        try:
            success, msg, notes = self.xhs_apis.search_some_note(query, require_num, cookies_str, sort_type_choice, note_type, note_time, note_range, pos_distance, geo, proxies)
            if success:
                notes = list(filter(lambda x: x['model_type'] == "note", notes))
                logger.info(f'搜索关键词 {query} 笔记数量: {len(notes)}')
                for note in notes:
                    note_url = f"https://www.xiaohongshu.com/explore/{note['id']}?xsec_token={note['xsec_token']}"
                    note_list.append(note_url)
            if save_choice == 'all' or save_choice == 'excel':
                excel_name = query
            self.spider_some_note(note_list, cookies_str, base_path, save_choice, excel_name, proxies)
        except Exception as e:
            success = False
            msg = e
        logger.info(f'搜索关键词 {query} 笔记: {success}, msg: {msg}')
        return note_list, success, msg

    @staticmethod
    def resolve_short_url(short_url: str):
        """
        解析短链接获取真实URL
        :param short_url: 短链接URL
        :return: 真实URL
        """
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8'
            }
            # 使用GET请求并跟随重定向
            response = requests.get(short_url, headers=headers, allow_redirects=True, timeout=10)
            real_url = response.url
            logger.info(f'解析短链接 {short_url} -> {real_url}')
            return real_url
        except Exception as e:
            logger.error(f'解析短链接失败 {short_url}: {e}')
            return short_url

if __name__ == '__main__':
    """
        此文件为爬虫的入口文件，可以直接运行
        apis/xhs_pc_apis.py 为爬虫的api文件，包含小红书的全部数据接口，可以继续封装
        apis/xhs_creator_apis.py 为小红书创作者中心的api文件
        感谢star和follow
    """

    cookies_str, base_path = init()
    data_spider = Data_Spider()
    """
        save_choice: all: 保存所有的信息, media: 保存视频和图片（media-video只下载视频, media-image只下载图片，media都下载）, excel: 保存到excel
        save_choice 为 excel 或者 all 时，excel_name 不能为空
    """

    # ========== 爬取指定博主和笔记 ==========
    
    # 1. 从笔记链接提取用户信息并爬取该用户的所有笔记
    logger.info("=" * 50)
    logger.info("从笔记链接提取用户信息并爬取该用户的所有笔记...")
    logger.info("=" * 50)
    note_urls_from_users = [
        'https://www.xiaohongshu.com/discovery/item/68ee19d300000000070146f3?source=webshare&xhsshare=pc_web&xsec_token=AB-86jfG8MPpXj5hsC98RQEXgUoc9lqtMdHmBx7pIP-lw=&xsec_source=pc_share',  # 李李呀_LiLi的笔记
    ]
    for note_url in note_urls_from_users:
        try:
            # 将discovery/item格式转换为explore格式
            if '/discovery/item/' in note_url:
                note_id = note_url.split('/discovery/item/')[1].split('?')[0]
                xsec_token = note_url.split("xsec_token=")[1].split("&")[0] if "xsec_token=" in note_url else ""
                note_url = f'https://www.xiaohongshu.com/explore/{note_id}?xsec_token={xsec_token}'
            
            logger.info(f"处理笔记链接: {note_url}")
            note_list, success, msg = data_spider.spider_user_from_note_url(note_url, cookies_str, base_path, 'all', '', proxies=None)
            if success:
                logger.info(f"成功爬取用户的所有笔记，共 {len(note_list)} 条")
            else:
                logger.error(f"爬取失败: {msg}")
        except Exception as e:
            logger.error(f"处理笔记链接时出错: {e}")
    
    # 2. 爬取单独的笔记链接
    logger.info("=" * 50)
    logger.info("开始爬取单独的笔记...")
    logger.info("=" * 50)
    note_urls = [
        'https://www.xiaohongshu.com/discovery/item/6899c8b30000000023036a56?source=webshare&xhsshare=pc_web&xsec_token=CB6P8Q_5XuU8NqKln70Xr_9m4PxzItpEzqtNg6H2YnHxU=&xsec_source=pc_share',
        'https://www.xiaohongshu.com/discovery/item/689c5f60000000001c03457e?source=webshare&xhsshare=pc_web&xsec_token=CBGVIcwvNIzyamTpJS7G3kUX5AF9UFuiCW41ok5UuwznU=&xsec_source=pc_share',
    ]
    # 将discovery/item格式转换为explore格式
    converted_notes = []
    for url in note_urls:
        if '/discovery/item/' in url:
            note_id = url.split('/discovery/item/')[1].split('?')[0]
            converted_notes.append(f'https://www.xiaohongshu.com/explore/{note_id}?xsec_token={url.split("xsec_token=")[1].split("&")[0] if "xsec_token=" in url else ""}')
        else:
            converted_notes.append(url)
    data_spider.spider_some_note(converted_notes, cookies_str, base_path, 'all', '单独笔记')
    
    # 3. 爬取博主主页的所有笔记（通过小红书号）
    logger.info("=" * 50)
    logger.info("开始爬取博主主页...")
    logger.info("=" * 50)
    
    # 博主信息列表（用户名，小红书号）
    bloggers = [
        ('潘白雪', '959415797'),
        ('宋仁何', '112334484'),
        ('段公子DU_AN', '495788515'),
        ('沙丁魚的腦子', 'sdydnz001'),
        ('小怡同学', '66669999y'),
        ('李李呀_LiLi', ''),  # 未提供小红书号，使用之前的URL
    ]
    
    for blogger_name, red_id in bloggers:
        try:
            logger.info(f"正在处理博主: {blogger_name}")
            if red_id:
                # 通过小红书号搜索并爬取
                data_spider.spider_user_by_red_id(red_id, blogger_name, cookies_str, base_path, 'all', excel_name=blogger_name)
            else:
                # 如果没有小红书号，尝试使用之前的URL方法
                logger.info(f"博主 {blogger_name} 无小红书号，尝试其他方法...")
        except Exception as e:
            logger.error(f"爬取博主 {blogger_name} 时出错: {e}")
    
    logger.info("=" * 50)
    logger.info("所有爬取任务完成！")
    logger.info("=" * 50)
