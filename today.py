import datetime
from dateutil import relativedelta
import requests
import os
from lxml import etree
import time

# Only public data is read, through GitHub's REST API, so no personal access token is needed.
# The workflow's built-in GITHUB_TOKEN is optional and only raises the rate limit.
HEADERS = {'authorization': 'bearer '+ os.environ['GITHUB_TOKEN']} if os.environ.get('GITHUB_TOKEN') else {}
USER_NAME = os.environ['USER_NAME'] # 'brandonsaldan'
QUERY_COUNT = {'public_repos': 0, 'get_specific_repo_stars': 0}


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


def simple_request(func_name, path, params=None):
    """
    Returns the JSON from a GitHub REST API GET, or raises an Exception if the response does not succeed.
    Retries without the token if GitHub refuses it, since everything requested here is public.
    """
    query_count(func_name)
    request = requests.get('https://api.github.com' + path, params=params, headers=HEADERS)
    if request.status_code in (401, 403) and HEADERS:
        print('   ' + func_name + ' warning: token refused (' + str(request.status_code) + '), retrying without it')
        request = requests.get('https://api.github.com' + path, params=params)
    if request.status_code == 200:
        return request.json()
    raise Exception(func_name, ' has failed with a', request.status_code, request.text, QUERY_COUNT)


def public_repos(username):
    """
    Returns every public repository owned by the user, fetched 100 at a time
    """
    repos, page = [], 1
    while True:
        batch = simple_request(public_repos.__name__, '/users/' + username + '/repos', {'type': 'owner', 'per_page': 100, 'page': page})
        repos += batch
        if len(batch) < 100:
            return repos
        page += 1


def stars_counter(repos):
    """
    Count total stars in repositories owned by me
    """
    return sum(repo['stargazers_count'] for repo in repos)


def get_specific_repo_stars(owner, repo_name):
    """
    Gets the star count for a specific repository
    """
    return simple_request(get_specific_repo_stars.__name__, '/repos/' + owner + '/' + repo_name)['stargazers_count']


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
    if new_text is None: # leave the existing value in place
        return
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
    repos, repo_time = perf_counter(public_repos, USER_NAME)
    formatter('public repos', repo_time)
    repo_data = len(repos)
    star_data = stars_counter(repos)

    try:
        nocturne_image_stars = get_specific_repo_stars('usenocturne', 'nocturne-image')
        nocturne_ui_stars = get_specific_repo_stars('usenocturne', 'nocturne-ui')
        org_stars = nocturne_image_stars + nocturne_ui_stars
        if star_data is not None:
            star_data += org_stars
        print(f"   Additional stars: {org_stars} (from usenocturne org)")
    except Exception as e:
        print(f"   Failed to get org stars: {str(e)}")
        star_data = None

    if star_data is None:
        print('   Star count is incomplete, keeping the previous value. See the warnings above.')

    svg_overwrite('dark_mode.svg', age_data, repo_data, star_data)
    svg_overwrite('light_mode.svg', age_data, repo_data, star_data)

    print('{:<21}'.format('Total function time:'), '{:>11}'.format('%.4f' % (age_time + repo_time)), ' s', sep='')

    print('Total GitHub REST API calls:', '{:>6}'.format(sum(QUERY_COUNT.values())))
    for funct_name, count in QUERY_COUNT.items(): print('{:<28}'.format('   ' + funct_name + ':'), '{:>6}'.format(count))
