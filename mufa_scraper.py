import requests
import bs4
import re
import csv
import time


def scrape_teams(session, parent_league_id):
    """Gets all the team IDs, and the sub-league ID for each team.
    Takes parameter parent_league_id, which is the integer ID for the main
    league (e.g. Summer Swiss 2013).
    Returns a list of teams and leagues."""
    html_response = session.get("http://sandlotsports.biz/teams/",
                                params={"leagueid": parent_league_id})
    html_file = html_response.text
    soup = bs4.BeautifulSoup(html_file, 'lxml')

    teams_table = soup.find('table')  # Just get first table
    # Could replace this with a generator
    table_rows = teams_table.select('tr')  # Select all tables
    teams_list = []
    # Create rows for a list of teams
    for row in table_rows:
        team_name = row.find('td', class_='teamName').get_text()
        # From the URL of the team's page, we can get team/league ID
        url = row.find('td', class_='teamName').find('a')['href']
        # Get the team ID using regex
        teamid_regex = re.compile('teamid=\d{1,6}', re.IGNORECASE)
        teamid_match = teamid_regex.search(url)
        team_id = ''.join(x for x in teamid_match.group() if x.isdigit())
        # Get the league ID using regex
        leagueid_regex = re.compile('leagueid=\d{1,6}', re.IGNORECASE)
        leagueid_match = leagueid_regex.search(url)
        league_id = ''.join(x for x in leagueid_match.group() if x.isdigit())

        teams_list.append((team_name, team_id, league_id))
    print(html_response.headers)
    return teams_list


def scrape_scores(session, team_id, league_id):
    """Scrapes the game results table for a specific team in a league.
    Writes rows of data to a tab-delimited text file."""
    html_response = session.get("http://sandlotsports.biz/teams/",
                                params={"teamid": team_id,
                                        "leagueid": league_id}
                                )
    html_file = html_response.text

    # Create a BeautifulSoup object from the file, parsing the HTML
    soup = bs4.BeautifulSoup(html_file, 'lxml')

    try:
        # Get team name from the header
        team_header = soup.find('h2', id='pageName')
        # Team naem comes after the header in the DOM
        team_name = team_header.next_element
    # If there are problems here, log the team/league for investigation
    except:
        with open('mufa_errors.txt', 'a', encoding='utf-8',
                  newline='') as errorf:
            error_writer = csv.writer(errorf, dialect='excel-tab')
            error_writer.writerow((team_id, league_id))

    # Get team rating if available
    try:
        # The next thing after "Self Rating: "
        team_rating = team_header.find('br').next_element[13:]
    except AttributeError:
        team_rating = ''
        # If there's no rating, then the site usually appends '(-)' to the name
        team_name = team_name.replace(' (-)', '')
    try:
        # Get just the <table> Tag with scores/games
        games_table = soup.select('table#upcomingGames')[0]

        # Identify where each column will be in the table (this will vary based
        # on the season; for example, Fall has no self-ratings.)
        header_row = [header for header in games_table.find('tr').contents
                      if type(header) is bs4.element.Tag]

        header_dict = {}
        # Strip out the HTML tags from each header
        for i, header in enumerate(header_row):
            header_name = (str(header).replace('</br>', '')
                           .replace('<br>', ' ').replace('<br/>', ' ')
                           .replace('<th>', '').replace('</th>', ''))
            header_dict[header_name] = i

        # Create a list of bs4 Tags for table rows
        # Only get the rows with a CSS class, so we don't grab the header row
        table_rows = games_table.find_all('tr', class_=True)

        # In Python 3, we open the file not in "binary" mode
        with open('mufa_test.txt', 'a', encoding='utf-8', newline='') as fout:
            for row in table_rows:
                # Set up a variable for an iterable of the row's contents
                r = row.contents

                # If there's no score, skip the row
                if not ''.join(x for x in r[header_dict['Score']].get_text()
                               if x.isdigit()):
                    print("No score found for " + r[0].get_text())
                    continue

                # Get game location, stripping out map/diagram links
                # Separate out the park and field names as well
                game_loc = (r[header_dict['Field']].get_text()
                            .replace(' (', '')
                            .replace(')', '').replace("Map", '')
                            .replace("Diagram", ''))

                field_names = ['A', 'B', 'C', 'D', 'E', 'F', 'North',
                               'South', 'East', 'West', '1', '2', '3',
                               '4', '5', '6', '7', '8']

                if game_loc.split()[-1] in field_names and ':' not in game_loc:
                    game_park = ' '.join(game_loc.split()[:-1])
                    game_field = game_loc.split()[-1]
                elif game_loc.split()[-1] in field_names and ':' in game_loc:
                    game_park = ' '.join(game_loc.split()[:-1])
                    game_field = ''
                else:
                    game_park = game_loc
                    game_field = game_loc

                # Add all columns that will always exist
                data_row = [
                    # Get date, stripped of other stuff
                    r[header_dict['Date']].get_text()[
                        0:r[header_dict['Date']].get_text().find(' ')],
                    team_id,  # Team ID, which gets passed in to function
                    league_id,  # League ID, passed into the function
                    team_name,  # Team name var from the top
                    # Get opponent; strip their score, which is typically
                    # displayed in parens
                    r[header_dict['Opponent']].get_text()[
                          0:r[header_dict['Opponent']].get_text().find('(')-1],
                    # Get result, without the "c" captain's link
                    r[header_dict['Win or Loss']].get_text()[
                        0:
                        r[header_dict['Win or Loss']].get_text().find(' ')-1],
                    # Get scores, with only the digits (remove weird chars)
                    ''.join(x for x in r[header_dict['Score']].get_text()
                            if x.isdigit()),
                    ''.join(x for x in r[header_dict['Opp. Score']].get_text()
                            if x.isdigit()),
                    # Game location
                    game_loc,
                    game_park,
                    game_field,
                    r[header_dict['Game Time']].get_text(),
                    team_rating
                    ]

                # Append opponent's rating, which may or may not exist,
                # depending on the season
                try:
                    data_row.append(r[header_dict['Self Rtg']].get_text())
                except KeyError:
                    data_row.append('')

                print("Adding row to file:\n{0}".format(data_row))

                mufa_writer = csv.writer(fout, dialect='excel-tab')
                mufa_writer.writerow(data_row)
    except:  # Log any team/league IDs that caused an error, for investigation
        with open('mufa_errors.txt', 'a', encoding='utf-8',
                  newline='') as errorf:
            error_writer = csv.writer(errorf, dialect='excel-tab')
            error_writer.writerow((team_id, league_id))
    # Add a time delay to be gentle on the server
    time.sleep(15)

if __name__ == '__main__':
    with requests.Session() as sess:
        parent_league_id = input("Please enter the parent league ID: ")
        teams_list = scrape_teams(sess, parent_league_id)
        # For each team row in teams_list, call scrape_scores
        for team_name, team_id, league_id in teams_list:
            scrape_scores(sess, team_id, league_id)
