import datetime
from abc import ABCMeta, abstractmethod

import log
import re

from app.filter import Filter
from app.helper import ProgressHelper
from app.media import Media
from app.media.meta import MetaInfo
from app.utils.types import MediaType, SearchType, ProgressKey


class _IIndexClient(metaclass=ABCMeta):
    # 索引器ID
    client_id = ""
    # 索引器类型
    client_type = ""
    # 索引器名称
    client_name = ""

    media = None
    progress = None
    filter = None

    def __init__(self):
        self.media = Media()
        self.filter = Filter()
        self.progress = ProgressHelper()

    @abstractmethod
    def match(self, ctype):
        """
        匹配实例
        """
        pass

    @abstractmethod
    def get_status(self):
        """
        检查连通性
        """
        pass

    @abstractmethod
    def get_type(self):
        """
        获取类型
        """
        pass

    @abstractmethod
    def get_client_id(self):
        """
        获取索引器id
        """
        pass

    @abstractmethod
    def get_indexers(self):
        """
        :return:  indexer 信息 [(indexerId, indexerName, url)]
        """
        pass

    @abstractmethod
    def search(self, order_seq,
               indexer,
               key_word,
               filter_args: dict,
               match_media,
               in_from: SearchType):
        """
        根据关键字多线程搜索
        """
        pass

    def match_(self, match_media, item):
        imdbid = item.get("imdbid")
        torrent_name = item.get('title')
        description = item.get('description')
        # 识别种子名称
        imdbid_match = False
        name_match = False
        year_match = False

        def sim_(s):
            # 正则表达式匹配中文字符、英文字母和数字
            # \u4e00-\u9fff 匹配中文字符
            # a-zA-Z 匹配英文字母
            # 0-9 匹配数字
            pattern = re.compile(r'[^\u4e00-\u9fffA-Za-z0-9]')
            return re.sub(pattern, '', s)
        def sim_in_(a,b):
            return sim_(a) in sim_(b)
        description = description if description else ""
        torrent_name = torrent_name if torrent_name else ""
        imdbid_match = imdbid and match_media.imdb_id and str(imdbid) == str(match_media.imdb_id)

        name_match = sim_in_(match_media.org_string, torrent_name)  \
                    or sim_in_(match_media.original_title , torrent_name ) \
                    or sim_in_(match_media.org_string , description ) \
                    or sim_in_(match_media.original_title , description)

        total_year_list = []
        # 电影直接使用年份匹配
        if   match_media.year:
            total_year_list.append(match_media.year)
        
        # 如果有剧集信息
        if hasattr(match_media, 'tmdb_info') and hasattr(match_media.tmdb_info, 'seasons'):
            for tmp_seasons in match_media.tmdb_info.seasons:
                if hasattr(tmp_seasons,"air_date") and tmp_seasons.air_date:
                    season_yead = tmp_seasons.air_date.split("-")[0]
                    total_year_list.append(season_yead)

        def year_ok(year_):
             return (year_ in torrent_name) or (year_ in description)
        if len(total_year_list) == 0:
            year_match = True
        else:
            for year_ in total_year_list:
                if year_ok(year_):
                    year_match = True
                    break
        if not year_match:
            log.info(f"year匹配失败,目标year:")
        if not name_match:
            log.info(f"year匹配失败,目标name:{match_media.org_string} {match_media.original_title}")
        if (imdbid_match or name_match) and year_match :
            return  True
        
        log.info(f"imdb匹配{imdbid_match} 名字匹配{name_match} year匹配{year_match}")
        return  False
    
    def filter_search_results(self, result_array: list,
                              order_seq,
                              indexer,
                              filter_args: dict,
                              match_media,
                              start_time):
        """
        从搜索结果中匹配符合资源条件的记录
        """
        ret_array = []
        index_sucess = 0
        index_rule_fail = 0
        index_match_fail = 0
        index_error = 0
        for item in result_array:
            # 名称
            torrent_name = item.get('title')
            # 描述
            description = item.get('description')
            if not torrent_name:
                index_error += 1
                continue
            enclosure = item.get('enclosure')
            size = item.get('size')
            seeders = item.get('seeders')
            peers = item.get('peers')
            page_url = item.get('page_url')
            hit_and_run = item.get('hit_and_run')
            hr_days = item.get('hr_days')
            torrent_id = item.get('torrent_id')
            indexer_id = item.get('indexer_id')
            pubdate = item.get('pubdate')
            uploadvolumefactor = round(float(item.get('uploadvolumefactor')), 1) if item.get(
                'uploadvolumefactor') is not None else 1.0
            downloadvolumefactor = round(float(item.get('downloadvolumefactor')), 1) if item.get(
                'downloadvolumefactor') is not None else 1.0
            imdbid = item.get("imdbid")
            labels = item.get("labels")
            # 全匹配模式下，非公开站点，过滤掉做种数为0的
            if filter_args.get("seeders") and not indexer.public and str(seeders) == "0":
                log.info(f"【{self.client_name}】{torrent_name} 做种数为0")
                index_rule_fail += 1
                continue
            # 过滤做种人数
            filter_seeders = filter_args.get("filter_seeders")
            if filter_seeders and seeders < filter_seeders:
                log.info(f"【{self.client_name}】{torrent_name} 做种数小于 {filter_seeders}")
                index_rule_fail += 1
                continue
            # 识别种子名称
            meta_info = MetaInfo(title=torrent_name, subtitle=f"{labels} {description}")
            # 检查标题是否匹配季、集、年 
            # 这个检查提到最前，不确定merge了match_media后会不会让这个检查失效
            if not self.filter.is_torrent_match_sey(meta_info,
                                                    filter_args.get("season"),
                                                    filter_args.get("episode"),
                                                    filter_args.get("year")):
                log.info(
                    f"【{self.client_name}】{torrent_name} 识别为 {meta_info.type.value}/"
                    f"{meta_info.get_title_string()}/{meta_info.get_season_episode_string()} 不匹配季/集/年份")
                index_match_fail += 1
                continue

            # 根据种子信息快速判断是否匹配
            if match_media:
                if not self.match_(match_media, item):
                    log.info(f"【{self.client_name}】{torrent_name} 快速匹配不通过")
                    index_match_fail+=1
                    continue
                else:
                    # 合并媒体数据
                    meta_info = self.media.merge_media_info(meta_info, match_media)
            
            # 识别种子名称
            if not meta_info.get_name():
                log.info(f"【{self.client_name}】{torrent_name} 无法识别到名称")
                index_match_fail += 1
                continue
            # 大小及促销等
            meta_info.set_torrent_info(size=size,
                                       imdbid=imdbid,
                                       upload_volume_factor=uploadvolumefactor,
                                       download_volume_factor=downloadvolumefactor,
                                       labels=labels)

            # 先过滤掉可以明确的类型
            if meta_info.type == MediaType.TV and filter_args.get("type") == MediaType.MOVIE:
                log.info(
                    f"【{self.client_name}】{torrent_name} 是 {meta_info.type.value}，"
                    f"不匹配类型：{filter_args.get('type').value}")
                index_rule_fail += 1
                continue
            # 检查订阅过滤规则匹配
            match_flag, res_order, match_msg = self.filter.check_torrent_filter(
                meta_info=meta_info,
                filter_args=filter_args,
                uploadvolumefactor=uploadvolumefactor,
                downloadvolumefactor=downloadvolumefactor)
            if not match_flag:
                log.info(f"【{self.client_name}】{match_msg}")
                index_rule_fail += 1
                continue
            # 识别媒体信息
            if not match_media:
                # 不过滤
                media_info = meta_info
            else:
                # 上面已经通过match_匹配通过了，不再查询tmdb信息来匹配（查询tdmb太慢了）
                media_info = meta_info
                # 过滤类型
                if filter_args.get("type"):
                    if (filter_args.get("type") == MediaType.TV and media_info.type == MediaType.MOVIE) \
                            or (filter_args.get("type") == MediaType.MOVIE and media_info.type == MediaType.TV):
                        log.info(
                            f"【{self.client_name}】{torrent_name} 是 {media_info.type.value}/"
                            f"{media_info.tmdb_id}，不是 {filter_args.get('type').value}")
                        index_rule_fail += 1
                        continue
                # 洗版
                if match_media.over_edition:
                    # 季集不完整的资源不要
                    if media_info.type != MediaType.MOVIE \
                            and media_info.get_episode_list():
                        log.info(f"【{self.client_name}】"
                                 f"{media_info.get_title_string()}{media_info.get_season_string()} "
                                 f"正在洗版，过滤掉季集不完整的资源：{torrent_name} {description}")
                        continue
                    # 检查优先级是否更好
                    if match_media.res_order \
                            and int(res_order) <= int(match_media.res_order):
                        log.info(
                            f"【{self.client_name}】"
                            f"{media_info.get_title_string()}{media_info.get_season_string()} "
                            f"正在洗版，已洗版优先级：{100 - int(match_media.res_order)}，"
                            f"当前资源优先级：{100 - int(res_order)}，"
                            f"跳过低优先级或同优先级资源：{torrent_name}"
                        )
                        continue

            # 不完整的资源
            if meta_info.get_episode_list() :
                # 非电影，只有最后一季才下载不完整的资源，不然单集了
                if meta_info.tmdb_info and hasattr(meta_info.tmdb_info, "seasons"):
                    last_season_num = meta_info.tmdb_info.seasons[-1].season_number
                    if str(last_season_num) not in meta_info.get_season_string():
                        index_rule_fail += 1
                        log.info(f"【{self.client_name}】"
                                 f"{meta_info.get_title_string()}{meta_info.get_season_string()} "
                                 f"非最新季，过滤掉季集不完整的资源：{torrent_name} {description}")
                        continue

            # 匹配到了
            log.info(
                f"【{self.client_name}】{torrent_name} {description} 识别为 {media_info.get_title_string()} "
                f"{media_info.get_season_episode_string()} 匹配成功")
            media_info.set_torrent_info(site=indexer.name,
                                        site_order=order_seq,
                                        enclosure=enclosure,
                                        res_order=res_order,
                                        filter_rule=filter_args.get("rule"),
                                        size=size,
                                        seeders=seeders,
                                        peers=peers,
                                        description=description,
                                        page_url=page_url,
                                        upload_volume_factor=uploadvolumefactor,
                                        download_volume_factor=downloadvolumefactor,
                                        hit_and_run=hit_and_run,
                                        hr_days=hr_days,
                                        torrent_id=torrent_id,
                                        indexer_id=indexer_id,
                                        pubdate=pubdate)
            if media_info not in ret_array:
                index_sucess += 1
                ret_array.append(media_info)
            else:
                index_rule_fail += 1
        # 循环结束
        # 计算耗时
        end_time = datetime.datetime.now()
        log.info(
            f"【{self.client_name}】{indexer.name} {len(result_array)} 条数据中，"
            f"过滤 {index_rule_fail}，"
            f"不匹配 {index_match_fail}，"
            f"错误 {index_error}，"
            f"有效 {index_sucess}，"
            f"耗时 {(end_time - start_time).seconds} 秒")
        self.progress.update(ptype=ProgressKey.Search,
                             text=f"{indexer.name} {len(result_array)} 条数据中，"
                                  f"过滤 {index_rule_fail}，"
                                  f"不匹配 {index_match_fail}，"
                                  f"错误 {index_error}，"
                                  f"有效 {index_sucess}，"
                                  f"耗时 {(end_time - start_time).seconds} 秒")
        return ret_array
