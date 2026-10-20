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
ORG_NAME = 'usenocturne' # this organization's own (non-fork) repositories count toward my stars, commits, and lines of code
QUERY_COUNT = {'public_repos': 0, 'follower_getter': 0, 'contributor_stats': 0}
LINE_WIDTH = 60 # every info line is padded with dots to this many characters


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


def public_repos(path, repo_type):
    """
    Returns every public repository at a /users/<name>/repos or /orgs/<name>/repos path, fetched 100 at a time
    """
    repos, page = [], 1
    while True:
        batch = simple_request(public_repos.__name__, path, {'type': repo_type, 'per_page': 100, 'page': page})
        repos += batch
        if len(batch) < 100:
            return repos
        page += 1


def follower_getter(username):
    """
    Returns the number of followers of the user
    """
    return simple_request(follower_getter.__name__, '/users/' + username)['followers']


def contributor_stats(full_names, rounds=6, wait=15):
    """
    Returns my (commits, additions, deletions, repos contributed to) across the given repositories,
    from GitHub's per-repository contributor statistics. GitHub computes these in the background and
    answers 202 until they're ready, so repositories still computing are retried a few times.
    Returns None if any repository never became ready, since the totals would be incomplete.
    """
    commits = additions = deletions = contributed = 0
    pending = list(full_names)
    for attempt in range(rounds):
        still_pending = []
        for name in pending:
            query_count(contributor_stats.__name__)
            request = requests.get('https://api.github.com/repos/' + name + '/stats/contributors', headers=HEADERS)
            if request.status_code in (401, 403) and HEADERS:
                request = requests.get('https://api.github.com/repos/' + name + '/stats/contributors')
            if request.status_code == 202:
                still_pending.append(name); continue
            if request.status_code == 204: # empty repository
                continue
            if request.status_code != 200:
                raise Exception(contributor_stats.__name__, ' has failed with a', request.status_code, request.text, QUERY_COUNT)
            for author in request.json():
                if author.get('author') and author['author']['login'].lower() == USER_NAME.lower():
                    contributed += 1
                    commits += author['total']
                    additions += sum(week['a'] for week in author['weeks'])
                    deletions += sum(week['d'] for week in author['weeks'])
        pending = still_pending
        if not pending:
            return commits, additions, deletions, contributed
        print(f'   {len(pending)} repos still computing contributor stats, retrying in {wait} s')
        time.sleep(wait)
    print('   Contributor stats never finished for: ' + ', '.join(pending))
    return None


def stars_counter(repos):
    """
    Count total stars in repositories owned by me
    """
    return sum(repo['stargazers_count'] for repo in repos)


def svg_overwrite(filename, age_data, repo_data, contrib_data, star_data, commit_data, follower_data, loc_data):
    """
    Parse SVG files and update elements with my age, repositories, stars, commits, followers, and lines of code
    """
    tree = etree.parse(filename)
    root = tree.getroot()
    justify_format(root, 'age_data', age_data, 49)
    justify_format(root, 'repo_data', repo_data, 6)
    justify_format(root, 'contrib_data', contrib_data)
    justify_format(root, 'star_data', star_data, 14)
    justify_format(root, 'commit_data', commit_data, 23)
    justify_format(root, 'follower_data', follower_data, 10)
    if loc_data is not None:
        justify_format(root, 'loc_data', loc_data[2])
        justify_format(root, 'loc_add', loc_data[0])
        justify_format(root, 'loc_del', loc_data[1])
    fit_lines(root)
    align_loc(root)
    tree.write(filename, encoding='utf-8', xml_declaration=True)


def info_lines(root):
    """
    Returns the elements of each line of text in the SVG, grouped by the tspans that start a new line
    """
    lines = []
    for text in root.iter('{http://www.w3.org/2000/svg}text'):
        for child in text:
            if child.get('x') is not None:
                lines.append([])
            if lines:
                lines[-1].append(child)
    return lines


def line_text(line):
    """
    Returns the characters a line renders, as one string
    """
    return ''.join((e.text or '') + (e.tail or '').replace('\n', '') for e in line)


def fit_lines(root):
    """
    Pads or trims the first run of dots on each info line so every line is exactly LINE_WIDTH characters,
    whatever the lengths of the numbers on it
    """
    for line in info_lines(root):
        dots = next((e for e in line if (e.get('id') or '').endswith('_dots') and (e.text or '').strip()), None)
        if dots is None:
            continue
        count = max(1, dots.text.count('.') + LINE_WIDTH - len(line_text(line)))
        dots.text = ' ' + '.' * count + ' '


def align_loc(root):
    """
    Lines up the Lines of Code total with the commit count above it: the total ends where the commit count
    ends and its '(' sits under the '|'. The gap between the added and deleted counts takes up the rest,
    so the line still ends at LINE_WIDTH.
    """
    lines = info_lines(root)
    commits = next((line_text(l) for l in lines if any(e.get('id') == 'commit_data' for e in l)), None)
    loc = next((l for l in lines if any(e.get('id') == 'loc_data' for e in l)), None)
    if commits is None or loc is None or '|' not in commits:
        return
    bar = commits.index('|')
    elements = {e.get('id'): e for e in loc}
    head = line_text(loc[:loc.index(elements['loc_data_dots'])])  # '. Lines of Code:'
    dots = bar - 1 - len(head) - 2 - len(elements['loc_data'].text)
    elements['loc_data_dots'].text = ' ' + '.' * max(1, dots) + ' '
    elements['loc_del_dots'].text = ''
    spaces = LINE_WIDTH - len(line_text(loc))
    elements['loc_del_dots'].text = ' ' * max(0, spaces)


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
    repos, repo_time = perf_counter(public_repos, '/users/' + USER_NAME + '/repos', 'owner')
    formatter('public repos', repo_time)
    repo_data = len(repos)
    star_data = stars_counter(repos)

    org_repos = []
    try:
        org_repos = [repo for repo in public_repos('/orgs/' + ORG_NAME + '/repos', 'public') if not repo['fork']]
        org_stars = stars_counter(org_repos)
        star_data += org_stars
        print(f"   Additional stars: {org_stars} (from {len(org_repos)} {ORG_NAME} repos)")
    except Exception as e:
        print(f"   Failed to get org stars: {str(e)}")
        star_data = None

    if star_data is None:
        print('   Star count is incomplete, keeping the previous value. See the warnings above.')

    follower_data, follower_time = perf_counter(follower_getter, USER_NAME)
    formatter('followers', follower_time)

    stats, stats_time = perf_counter(contributor_stats, [repo['full_name'] for repo in repos + org_repos])
    formatter('contributor stats', stats_time)
    commit_data = contrib_data = loc_data = None
    if stats is None:
        print('   Commits and lines of code are incomplete, keeping the previous values.')
    else:
        commit_data, added, deleted, contrib_data = stats
        loc_data = ['{:,}'.format(added), '{:,}'.format(deleted), '{:,}'.format(added - deleted)]

    for card in ['dark_mode.svg', 'light_mode.svg']:
        svg_overwrite(card, age_data, repo_data, contrib_data, star_data, commit_data, follower_data, loc_data)

    print('{:<21}'.format('Total function time:'), '{:>11}'.format('%.4f' % (age_time + repo_time + follower_time + stats_time)), ' s', sep='')

    print('Total GitHub REST API calls:', '{:>6}'.format(sum(QUERY_COUNT.values())))
    for funct_name, count in QUERY_COUNT.items(): print('{:<28}'.format('   ' + funct_name + ':'), '{:>6}'.format(count))
