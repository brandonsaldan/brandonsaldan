import datetime
from dateutil import relativedelta
import requests
import os
from lxml import etree
import time

# Fine-grained personal access token with All Repositories access:
# Repository permissions: read:Metadata
HEADERS = {'authorization': 'bearer '+ os.environ['ACCESS_TOKEN']}
USER_NAME = os.environ['USER_NAME'] # 'brandonsaldan'
QUERY_COUNT = {'graph_repos_stars': 0, 'get_specific_repo_stars': 0}


def daily_readme(birthday):
    """
    Returns the length of time since I was born
    e.g. 'XX years, XX months, XX days'
    """
    diff = relativedelta.relativedelta(datetime.datetime.today(), birthday)
    return '{} {}, {} {}, {} {}{}'.format(
        diff.years, 'year' + format_plural(diff.years),
        diff.months, 'month' + format_plural(diff.months),
        diff.days, 'day' + format_plural(diff.days),
        ' 🎂' if (diff.months == 0 and diff.days == 0) else '')


def format_plural(unit):
    """
    Returns a properly formatted number
    e.g.
    'day' + format_plural(diff.days) == 5
    >>> '5 days'
    'day' + format_plural(diff.days) == 1
    >>> '1 day'
    """
    return 's' if unit != 1 else ''


def simple_request(func_name, query, variables):
    """
    Returns a request, or raises an Exception if the response does not succeed.
    """
    request = requests.post('https://api.github.com/graphql', json={'query': query, 'variables':variables}, headers=HEADERS)
    if request.status_code == 200:
        return request
    if request.status_code == 401:
        raise Exception(func_name + ' got a 401: ACCESS_TOKEN is missing, invalid, or expired. Generate a new token and update the repository secret.')
    raise Exception(func_name, ' has failed with a', request.status_code, request.text, QUERY_COUNT)


def graph_repos_stars(count_type, owner_affiliation, cursor=None, star_total=0):
    """
    Uses GitHub's GraphQL v4 API to return my total repository or star count.
    Stars are paginated 100 repositories at a time.
    """
    query_count('graph_repos_stars')
    query = '''
    query ($owner_affiliation: [RepositoryAffiliation], $login: String!, $cursor: String) {
        user(login: $login) {
            repositories(first: 100, after: $cursor, ownerAffiliations: $owner_affiliation) {
                totalCount
                edges {
                    node {
                        ... on Repository {
                            nameWithOwner
                            stargazers {
                                totalCount
                            }
                        }
                    }
                }
                pageInfo {
                    endCursor
                    hasNextPage
                }
            }
        }
    }'''
    variables = {'owner_affiliation': owner_affiliation, 'login': USER_NAME, 'cursor': cursor}
    request = simple_request(graph_repos_stars.__name__, query, variables)
    repositories = request.json()['data']['user']['repositories']
    if count_type == 'repos':
        return repositories['totalCount']
    star_total += stars_counter(repositories['edges'])
    if repositories['pageInfo']['hasNextPage']:
        return graph_repos_stars(count_type, owner_affiliation, repositories['pageInfo']['endCursor'], star_total)
    return star_total


def stars_counter(data):
    """
    Count total stars in repositories owned by me
    """
    total_stars = 0
    for node in data: total_stars += node['node']['stargazers']['totalCount']
    return total_stars


def get_specific_repo_stars(owner, repo_name):
    """
    Gets the star count for a specific repository
    """
    query_count('get_specific_repo_stars')
    query = '''
    query ($owner: String!, $repo_name: String!) {
        repository(owner: $owner, name: $repo_name) {
            stargazers {
                totalCount
            }
        }
    }'''
    variables = {'owner': owner, 'repo_name': repo_name}
    request = simple_request(get_specific_repo_stars.__name__, query, variables)
    if request.json()['data']['repository'] is not None:
        return request.json()['data']['repository']['stargazers']['totalCount']
    return 0


def svg_overwrite(filename, age_data, repo_data, star_data):
    """
    Parse SVG files and update elements with my age, repositories, and stars
    """
    tree = etree.parse(filename)
    root = tree.getroot()
    justify_format(root, 'age_data', age_data, 49)
    justify_format(root, 'repo_data', repo_data, 26)
    justify_format(root, 'star_data', star_data, 13)
    tree.write(filename, encoding='utf-8', xml_declaration=True)


def justify_format(root, element_id, new_text, target_length=0):
    """
    Updates and formats the text of the element, and modifies the dots to align text

    Parameters:
    - root: XML root element
    - element_id: ID of the element to update
    - new_text: New text value
    - target_length: Target total length (text + dots)
    """
    if isinstance(new_text, int):
        new_text = f"{'{:,}'.format(new_text)}"
    new_text = str(new_text)
    find_and_replace(root, element_id, new_text)

    if target_length > 0:
        dots_needed = max(0, target_length - len(new_text))
        dot_string = ' ' + ('.' * dots_needed) + ' ' if dots_needed > 0 else ''
        find_and_replace(root, f"{element_id}_dots", dot_string)


def find_and_replace(root, element_id, new_text):
    """
    Finds the element in the SVG file and replaces its text with a new value
    """
    element = root.find(f".//*[@id='{element_id}']")
    if element is not None:
        element.text = new_text


def query_count(funct_id):
    """
    Counts how many times the GitHub GraphQL API is called
    """
    global QUERY_COUNT
    QUERY_COUNT[funct_id] += 1


def perf_counter(funct, *args):
    """
    Calculates the time it takes for a function to run
    Returns the function result and the time differential
    """
    start = time.perf_counter()
    funct_return = funct(*args)
    return funct_return, time.perf_counter() - start


def formatter(query_type, difference, funct_return=False, whitespace=0):
    """
    Prints a formatted time differential
    Returns formatted result if whitespace is specified, otherwise returns raw result
    """
    print('{:<23}'.format('   ' + query_type + ':'), sep='', end='')
    print('{:>12}'.format('%.4f' % difference + ' s ')) if difference > 1 else print('{:>12}'.format('%.4f' % (difference * 1000) + ' ms'))
    if whitespace:
        return f"{'{:,}'.format(funct_return): <{whitespace}}"
    return funct_return


if __name__ == '__main__':
    """
    Based on Andrew Grant's (Andrew6rant) profile README script
    """
    print('Calculation times:')
    age_data, age_time = perf_counter(daily_readme, datetime.datetime(2002, 12, 23))
    formatter('age calculation', age_time)
    star_data, star_time = perf_counter(graph_repos_stars, 'stars', ['OWNER'])
    formatter('star count', star_time)

    try:
        nocturne_image_stars = get_specific_repo_stars('usenocturne', 'nocturne-image')
        nocturne_ui_stars = get_specific_repo_stars('usenocturne', 'nocturne-ui')
        org_stars = nocturne_image_stars + nocturne_ui_stars
        star_data += org_stars
        print(f"   Additional stars: {org_stars} (from usenocturne org)")
    except Exception as e:
        print(f"   Failed to get org stars: {str(e)}")

    repo_data, repo_time = perf_counter(graph_repos_stars, 'repos', ['OWNER'])
    formatter('repo count', repo_time)

    svg_overwrite('dark_mode.svg', age_data, repo_data, star_data)
    svg_overwrite('light_mode.svg', age_data, repo_data, star_data)

    print('{:<21}'.format('Total function time:'), '{:>11}'.format('%.4f' % (age_time + star_time + repo_time)), ' s', sep='')

    print('Total GitHub GraphQL API calls:', '{:>3}'.format(sum(QUERY_COUNT.values())))
    for funct_name, count in QUERY_COUNT.items(): print('{:<28}'.format('   ' + funct_name + ':'), '{:>6}'.format(count))
