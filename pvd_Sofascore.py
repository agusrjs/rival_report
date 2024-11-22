import pandas as pd
import re
import requests
import http.client
import json
import time
import os
from bs4 import BeautifulSoup
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


# Main functions


def get_teams_from_league(league_url):
    """
    Extracts team information from a Sofascore league URL.

    Args:
        league_url (str): The URL of the league page on Sofascore.

    Returns:
        list: A list of dictionaries containing team details, including name, ID, logo, league, country, season, and link.
    """
    teams_dic = []
    seen_links = []
    j = 0

    # Extract tournament_id and season_id from the URL
    parts = league_url.rstrip('/').split('/')
    tournament_id = parts[-1].split('#id:')[0]
    season_id = parts[-1].split('#id:')[1]

    # Use the get_tournament_standing function to get league data
    standings = get_tournament_standing(tournament_id, season_id)
    if standings is None:
        return teams_dic

    league = standings['league']
    country = standings['country']
    season = standings['season']
    teams_name = standings['teams_name']
    teams_id = standings['teams_id']

    try:
        response = requests.get(league_url)
        soup = BeautifulSoup(response.content, 'html.parser')
        links = soup.find_all('a', href=True)

        for link in links:
            href = link['href']

            if href not in seen_links:
                seen_links.append(href)

                if '/es/equipo/futbol/' in href:
                    full_link = 'https://www.sofascore.com' + href

                    if j < len(teams_name):
                        team_info = {
                            'team': teams_name[j],
                            'id': teams_id[j],
                            'logo': f'https://api.sofascore.app/api/v1/team/{teams_id[j]}/image',
                            'league': league,
                            'country': country,
                            'season': season,
                            'link': full_link
                        }
                        teams_dic.append(team_info)
                        j += 1

    except requests.exceptions.RequestException as e:
        print(f'Error during request: {e}')
    
    # Export to CSV
    os.makedirs('data', exist_ok=True)
    teams_df = pd.DataFrame(teams_dic)
    teams_df.to_csv('data/sofascore_teams.csv', index=False, encoding='utf-8')

    return teams_dic


def get_events_from_league(league_url):
    """
    Extracts event results from a Sofascore league URL.

    Args:
        league_url (str): The URL of the league page on Sofascore.

    Returns:
        list: A list of dictionaries containing event details, including round number, season, and link.
    """
    if not league_url.endswith(',tab:matches'):
        league_url += ',tab:matches'
    
    # Set up the driver
    driver = webdriver.Chrome()  # Or use `webdriver.Firefox()` if you are using Firefox
    events_dic = []  # List to store each event result as a separate row
    
    try:
        # Go to the URL
        driver.get(league_url)

        # Wait for the "By Rounds" tab to be clickable and click it
        wait = WebDriverWait(driver, 30)
        rounds_tab = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'div[data-tabid="2"]')))
        rounds_tab.click()

        # Wait for the content of the "By Rounds" tab to load
        wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, '[data-testid="event_cell"]')))

        # Get the season text
        season_element = driver.find_element(By.CSS_SELECTOR, 'div.Box.Flex.eJCdjm.bnpRyo .Text.nZQAT')
        season_text = season_element.text
        
        # Extract the season number from the text
        season = season_text.split(' ')[-1]  # Get the last element after the space

        # Initialize variables
        round_number = None
        
        while True:
            # Get the round text
            round_container = driver.find_element(By.CSS_SELECTOR, 'div.Box.gRmPLj')
            round_items = round_container.find_elements(By.CSS_SELECTOR, 'div.Text.nZQAT')
            
            selected_round = None
            for item in round_items:
                round_text = item.text
                if 'Round' or 'Ronda' in round_text:
                    selected_round = round_text
                    break

            # Extract the round number from the text
            current_round_number = selected_round.split(' ')[-1] if selected_round else 'Not found'
            
            if current_round_number == 'Not found':
                break
            
            round_number = int(current_round_number)
            
            # Extract event links for the current round
            event_cells = driver.find_elements(By.CSS_SELECTOR, '[data-testid="event_cell"]')
            for cell in event_cells:
                href = cell.get_attribute('href')
                if href and 'summary' not in href:  # Exclude links containing 'summary'
                    
                    # Extract tournament information
                    event_id = re.search(r'#id:(\d+)', href).group(1)
                    data = get_event_data(event_id)
                    league = data['event']['tournament']['name']
                    league_id = data['event']['tournament']['uniqueTournament']['id']
                    season_id = data['event']['season']['id']
                    country = data['event']['tournament']['category']['name']
                    home_team_id = data['event']['homeTeam']['id']
                    away_team_id = data['event']['awayTeam']['id']

                    round_result = {
                        'id': event_id,
                        'league': league,
                        'league_id': league_id,
                        'country': country,
                        'round': round_number,
                        'season': season,
                        'season_id': season_id,
                        'home_team_id': home_team_id,
                        'away_team_id': away_team_id,
                        'link': href
                    }

                    events_dic.append(round_result)

            # Check if we have reached round 1 and exit the loop if so
            if round_number <= 1:
                break

            # Try to go to the previous round
            try:
                previous_round_button = driver.find_element(By.CSS_SELECTOR, 'button.Button.iCnTrv')
                previous_round_button.click()
                # Wait a moment for the page to load
                WebDriverWait(driver, 10).until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, '[data-testid="event_cell"]')))
            except Exception as e:
                print(f"Error navigating to previous round: {e}")
                break

    finally:
        # Close the browser
        driver.quit()
    
    # Export to CSV
    os.makedirs('data', exist_ok=True)
    events_df = pd.DataFrame(events_dic)
    events_df.to_csv('data/sofascore_events.csv', index=False, encoding='utf-8')

    return events_dic


def get_players_from_teams(teams, delay=5):
    """
    Extracts player information from team URLs on Sofascore.

    Args:
        teams (list): List of dictionaries, each containing team details and URL.
        delay (int): Time to wait (in seconds) between requests to avoid overloading the server. Default is 5 seconds.

    Returns:
        list: A list of dictionaries with player information.
    """
    players_dic = []  # List to store player information
    repeated = []  # List to keep track of processed links

    for team in teams:
        time.sleep(delay)  # Respect the delay between requests

        team_name = team['team']
        season = team['season']
        league = team['league']
        country = team['country']
        url = team['link']

        # Make the request and parse the page content
        response = requests.get(url)
        soup = BeautifulSoup(response.content, 'html.parser')
        links = soup.find_all('a', href=True)

        for link in links:
            href = link['href']

            if href not in repeated:
                repeated.append(href)

                if '/es/jugador/' in href:
                    full_link = 'https://www.sofascore.com' + href
                    id = href.rstrip('/').split('/')[-1]
                    name = href.rstrip('/').split('/')[-2].replace('-', ' ').title()
                    profile = f'https://api.sofascore.app/api/v1/player/{id}/image'

                    # Create a dictionary for the player
                    player_info = {
                        'name': name,
                        'id': id,
                        'profile': profile,
                        'team': team_name,
                        'league': league,
                        'country': country,
                        'season': season,
                        'link': full_link
                    }
                    players_dic.append(player_info)

    # Export to CSV
    os.makedirs('data', exist_ok=True)
    players_df = pd.DataFrame(players_dic)
    players_df.to_csv('data/sofascore_players.csv', index=False, encoding='utf-8')

    return players_dic


def get_players_from_team_ids(teams, delay=5, language='es'):
    """
    Extracts player information from team URLs on Sofascore.

    Args:
        teams (list): List of dictionaries, each containing team details and URL.
        delay (int): Time to wait (in seconds) between requests to avoid overloading the server. Default is 5 seconds.

    Returns:
        list: A list of dictionaries with player information.
    """
    players_dic = []  # List to store player information
    repeated = []  # List to keep track of processed links

    for team in teams:
        time.sleep(delay)  # Respect the delay between requests

        team_id = team
        api_url = f'https://www.sofascore.com/api/v1/team/{team_id}'
        data = request_to_json(api_url)
        slug = data['team']['slug']
        
        # Default language is Spanish
        if language == 'es':
            url = f'https://www.sofascore.com/es/equipo/futbol/{slug}/{team_id}'
        else:
            url = f'https://www.sofascore.com/team/football/{slug}/{team_id}'

        # Make the request and parse the page content
        response = requests.get(url)
        soup = BeautifulSoup(response.content, 'html.parser')
        links = soup.find_all('a', href=True)

        for link in links:
            href = link['href']

            if href not in repeated:
                repeated.append(href)

                if '/es/jugador/' in href:
                    full_link = 'https://www.sofascore.com' + href
                    id = href.rstrip('/').split('/')[-1]
                    name = href.rstrip('/').split('/')[-2].replace('-', ' ').title()
                    profile = f'https://api.sofascore.app/api/v1/player/{id}/image'

                    # Create a dictionary for the player
                    player_info = {
                        'name': name,
                        'id': id,
                        'profile': profile,
                        'team_id': team_id,
                        'team_name': data['team']['name'],
                        'link': full_link
                    }
                    players_dic.append(player_info)

    # Export to CSV
    os.makedirs('data', exist_ok=True)
    players_df = pd.DataFrame(players_dic)
    players_df.to_csv('data/sofascore_players.csv', index=False, encoding='utf-8')

    return players_dic


def get_heatmap_from_players(players, delay=5):
    """
    Fetches heatmap data for a list of players from Sofascore API.

    Args:
        players (list of dict): List of player dictionaries with 'player_id'.
        delay (int): Delay in seconds between API requests to avoid rate limiting.

    Returns:
        DataFrame: Combined heatmap data for all players and tournaments.
    """
    
    dfs = []

    for player in players:
        time.sleep(delay)
        player_id = player['id']
        
        # Get tournaments for the current player
        try:
            tournaments = get_player_tournaments(player_id)
        except:
            continue
        
        # Loop through each tournament
        for _, row in tournaments.iterrows():
            league_id = row['tournaments_id']
            season_id = row['season_id']

            # Get heatmap for the current player, league, and season
            try:
                heatmap_tournament = get_heatmap(player_id, league_id, season_id)
                dfs.append(heatmap_tournament)
            except:
                continue

    # Concatenate all dataframes and save to CSV
    if dfs:
        os.makedirs('data', exist_ok=True)
        heatmaps_df = pd.concat(dfs, ignore_index=True)
        heatmaps_df.to_csv('data/sofascore_heatmap.csv', index=False, encoding='utf-8')
    else:
        heatmaps_df = pd.DataFrame()
        print("No heatmap data was collected.")

    return heatmaps_df


def get_lineups_from_events(events, delay=5):
    """
    Processes a list of events to extract and organize lineup data and average player positions.

    Args:
        events (list): List of dictionaries containing event information.
        delay (int): Time to wait (in seconds) between requests to avoid overloading the server. Default is 5 seconds.

    Returns:
        pd.DataFrame: A DataFrame containing the lineup data and average player positions for all processed events.
    """
    dfs = []  # Initialize a list to store DataFrames for each event

    for i in range(len(events)):
        time.sleep(delay)  # Wait before making the next request

        event = re.search(r'id:(\d+)', events[i]['link'])
        event_id = event.group(1) if event else 'unknown'
        
        try:
            data = get_event_data(event_id)
            status = data['event']['status']['type']

            if status == 'finished':
                # Get lineup, average positions, and event data
                lineups = get_lineups(event_id)
                average_positions = get_average_positions(event_id)

                # Extract and process formations for home and away teams
                home_formation = lineups['home']['formation']
                away_formation = lineups['away']['formation']

                # Process home formation
                home_groups_formation = home_formation.split('-')
                home_def = int(home_groups_formation[0])
                home_ata = int(home_groups_formation[-1])

                if len(home_groups_formation) == 4:
                    home_mid_0 = int(home_groups_formation[1])
                    home_mid_1 = 0
                    home_mid_2 = int(home_groups_formation[2])
                else:
                    home_mid_0 = 0
                    home_mid_1 = int(home_groups_formation[1])
                    home_mid_2 = 0

                # Process away formation
                away_groups_formation = away_formation.split('-')
                away_def = int(away_groups_formation[0])
                away_ata = int(away_groups_formation[-1])

                if len(away_groups_formation) == 4:
                    away_mid_0 = int(away_groups_formation[1])
                    away_mid_1 = 0
                    away_mid_2 = int(away_groups_formation[2])
                else:
                    away_mid_0 = 0
                    away_mid_1 = int(away_groups_formation[1])
                    away_mid_2 = 0

                # Initialize lists to store player data
                home = []
                away = []
                home_avg = []
                away_avg = []

                # Process home team players
                for j in range(len(lineups['home']['players'])):
                    player = lineups['home']['players'][j]
                    name = player['player']['name']
                    id = player['player']['id']
                    jersey = player['shirtNumber']
                    position = player.get('position', '')
                    substitute = player['substitute']
                    minutes = player.get('statistics', {}).get('minutesPlayed', 0)

                    if j < len(average_positions['home']):
                        avg_player = average_positions['home'][j]
                        avg_id = avg_player['player']['id']
                        averageX = avg_player['averageX']
                        averageY = avg_player['averageY']
                        pointsCount = avg_player['pointsCount']

                    order = j + 1
                    line, lat, pos = determine_position(order, home_def, home_mid_0, home_mid_1, home_mid_2, home_ata, substitute)
                    
                    # Append player data to home list
                    home.append([name, id, jersey, position, substitute, minutes, order, line, lat, pos])
                    home_avg.append([avg_id, averageX, averageY, pointsCount])

                # Process away team players
                for k in range(len(lineups['away']['players'])):
                    player = lineups['away']['players'][k]
                    name = player['player']['name']
                    id = player['player']['id']
                    jersey = player['shirtNumber']
                    position = player.get('position', '')
                    substitute = player['substitute']
                    minutes = player.get('statistics', {}).get('minutesPlayed', 0)

                    if k < len(average_positions['away']):
                        avg_player = average_positions['away'][k]
                        avg_id = avg_player['player']['id']
                        averageX = avg_player['averageX']
                        averageY = avg_player['averageY']
                        pointsCount = avg_player['pointsCount']

                    order = k + 1
                    line, lat, pos = determine_position(order, away_def, away_mid_0, away_mid_1, away_mid_2, away_ata, substitute)

                    # Append player data to away list
                    away.append([name, id, jersey, position, substitute, minutes, order, line, lat, pos])
                    away_avg.append([avg_id, averageX, averageY, pointsCount])

                # Create DataFrames for home and away teams
                home_df = pd.DataFrame(home, columns=['player', 'id', 'jersey', 'position', 'substitute', 'minutes', 'order', 'line', 'lat', 'pos'])
                home_df['local'] = 'Home'
                home_df['team'] = data['event']['homeTeam']['shortName']
                home_df['formation'] = home_formation
                home_df['defense'] = home_def
                home_df['midfield'] = home_mid_0 + home_mid_1 + home_mid_2
                home_df['attack'] = home_ata

                away_df = pd.DataFrame(away, columns=['player', 'id', 'jersey', 'position', 'substitute', 'minutes', 'order', 'line', 'lat', 'pos'])
                away_df['local'] = 'Away'
                away_df['team'] = data['event']['awayTeam']['shortName']
                away_df['formation'] = away_formation
                away_df['defense'] = away_def
                away_df['midfield'] = away_mid_0 + away_mid_1 + away_mid_2
                away_df['attack'] = away_ata

                # Create DataFrame for average player positions
                home_avg_position = pd.DataFrame(home_avg, columns=['avg_id', 'averageX', 'averageY', 'pointsCount'])
                away_avg_position = pd.DataFrame(away_avg, columns=['avg_id', 'averageX', 'averageY', 'pointsCount'])
                df_avg_position = pd.concat([home_avg_position, away_avg_position], ignore_index=True)
                df_avg_position.rename(columns={'avg_id': 'id'}, inplace=True)

                # Merge lineup data with average position data
                df = pd.concat([home_df, away_df], ignore_index=True)
                df_merged = pd.merge(df, df_avg_position, on='id', how='left')

                # Append the DataFrame to the list
                dfs.append(df_merged)

        except Exception as e:
            print(f"Error in processing lineup for event {event_id}: {e}")

    # Concatenate all DataFrames into one and save to CSV
    os.makedirs('data', exist_ok=True)
    lineups_df = pd.concat(dfs, ignore_index=True)
    lineups_df.to_csv('data/sofascore_lineup.csv', index=False, encoding='utf-8')

    return lineups_df


def get_results_from_events(events, delay=5):
    """
    Extracts match results from a list of events and returns a DataFrame.

    Args:
        events (list): A list of event dictionaries, each containing an 'id'.
        delay (int, optional): Delay in seconds between requests. Default is 5 seconds.

    Returns:
        pd.DataFrame: A DataFrame containing match results for each event.
    """
    # List to store DataFrames for each event
    dfs = []

    for event in events:
        # Respect the delay between requests to avoid overloading the server
        time.sleep(delay)

        # Extract the event ID from the event dictionary
        event_id = event['id']

        # Fetch event data using the event ID
        event_data = get_event_data(event_id)
        status = event_data['event']['status']['type']

        if status == 'finished':
            # Extract necessary details from the event data
            homeTeam_name = event_data['event']['homeTeam']['shortName']
            homeTeam_id = event_data['event']['homeTeam']['id']
            homeScore = int(event_data['event']['homeScore']['display'])
            awayTeam_name = event_data['event']['awayTeam']['shortName']
            awayTeam_id = event_data['event']['awayTeam']['id']
            awayScore = int(event_data['event']['awayScore']['display'])

            # Create a dictionary for the home team
            home_dic = {
                'event_id': event_id,
                'team': homeTeam_name,
                'team_id': homeTeam_id,
                'score_for': homeScore,
                'score_against': awayScore,
                'win': homeScore > awayScore,
                'draw': homeScore == awayScore,
                'loose': homeScore < awayScore,
                'local': 'Home'
            }

            # Create a dictionary for the away team
            away_dic = {
                'event_id': event_id,
                'team': awayTeam_name,
                'team_id': awayTeam_id,
                'score_for': awayScore,
                'score_against': homeScore,
                'win': awayScore > homeScore,
                'draw': awayScore == homeScore,
                'loose': awayScore < homeScore,
                'local': 'Away'
            }

            # Convert the dictionaries into DataFrames
            home_df = pd.DataFrame([home_dic])
            away_df = pd.DataFrame([away_dic])

            # Concatenate the home and away DataFrames into a single DataFrame
            df = pd.concat([home_df, away_df], ignore_index=True)

            # Append the DataFrame to the list
            dfs.append(df)

    # Concatenate all the DataFrames into one final DataFrame
    results_df = pd.concat(dfs, ignore_index=True)

    # Export the final DataFrame to a CSV file
    os.makedirs('data', exist_ok=True)
    results_df.to_csv('data/sofascore_results.csv', index=False, encoding='utf-8')

    return results_df


def get_attributes_from_players(players, delay=5):
    """
    Fetches attributes data for a list of players from Sofascore API.

    Args:
        players (list of dict): List of player dictionaries with 'player_id'.
        delay (int): Delay in seconds between API requests to avoid rate limiting.

    Returns:
        DataFrame: Combined attributes data for all players and tournaments.
    """
    
    dfs = []

    for player in players:
        time.sleep(delay)
        player_id = player['id']
        
        # Get attributes for the current player
        try:
            attributes = get_player_attributes(player_id)
            dfs.append(attributes)
        except:
            continue
        
    # Concatenate all dataframes and save to CSV
    if dfs:
        os.makedirs('data', exist_ok=True)
        attributes_df = pd.concat(dfs, ignore_index=True)
        attributes_df.to_csv('data/sofascore_attributes.csv', index=False, encoding='utf-8')
    else:
        attributes_df = pd.DataFrame()
        print("No attributes data was collected.")

    return attributes_df


def get_statistics_from_players(players, league_id, season_id, delay=5):
    """
    Fetches statistics data for a list of players from the Sofascore API.

    Args:
        players (list of dict): List of player dictionaries with 'id' key for player IDs.
        league_id (str): The league identifier for the statistics.
        season_id (str): The season identifier for the statistics.
        delay (int): Delay in seconds between API requests to avoid rate limiting.
        save_path (str): Path to save the resulting DataFrame as a CSV file.

    Returns:
        DataFrame: Combined statistics data for all players, or empty DataFrame if none collected.
    """
    
    dfs = []

    for player in players:
        time.sleep(delay)
        player_id = player['id']
        
        # Get statistics for the current player
        try:
            statistics = get_player_statistics(player_id, league_id, season_id)
            dfs.append(statistics)
        except:
            continue
        
    # Concatenate all dataframes and save to CSV
    if dfs:
        os.makedirs('data', exist_ok=True)
        statistics_df = pd.concat(dfs, ignore_index=True)
        statistics_df.to_csv('data/sofascore_players_statistics.csv', index=False, encoding='utf-8')
    else:
        statistics_df = pd.DataFrame()
        print("No statistics data was collected.")

    return statistics_df


def get_statistics_from_events(events, delay=5):
    """
    Fetches statistics data for a list of events from the Sofascore API.

    Args:
        events (list of dict): List of events.

    Returns:
        DataFrame: Combined statistics data for all events, or an empty DataFrame if none collected.
    """
    
    dfs = []

    for event in events:
        time.sleep(delay)  # Wait for the specified delay before making the next request
        event_id = event
        
        # Get statistics for the current event
        try:
            statistics = get_event_statistics(event_id)  # Call the function to get statistics
            dfs.append(statistics)  # Append the statistics DataFrame to the list
        except Exception as e:
            print(f"Error retrieving statistics for event {event_id}: {e}")
            continue  # Continue to the next event if there's an error
        
    # Concatenate all dataframes and save to CSV
    if dfs:
        os.makedirs('data', exist_ok=True)  # Create the directory if it doesn't exist
        statistics_df = pd.concat(dfs, ignore_index=True)  # Concatenate all DataFrames
        statistics_df.to_csv('data/sofascore_events_statistics.csv', index=False, encoding='utf-8')  # Save to CSV
    else:
        statistics_df = pd.DataFrame()  # Return an empty DataFrame if no data was collected
        print("No statistics data was collected.")

    return statistics_df


def get_momentum_from_events(events, delay=5):
    """
    Fetches and combines momentum data for a list of events, with an optional delay between requests.

    Args:
        events (list): List of event IDs to fetch momentum data for.
        delay (int, optional): Time in seconds to wait between API requests. Defaults to 5.

    Returns:
        pd.DataFrame: Combined DataFrame of momentum data for all events.
    """
    dfs = []

    for event in events:
        time.sleep(delay)
        event_id = event
        
        # Attempt to fetch momentum for the current event
        try:
            momentum = get_momentum(event_id)
            dfs.append(momentum)
        except Exception as e:
            print(f"Error retrieving momentum for event {event_id}: {e}")
            continue
        
    # Concatenate and save all DataFrames if data was collected
    if dfs:
        os.makedirs('data', exist_ok=True)
        momentum_df = pd.concat(dfs, ignore_index=True)
        momentum_df.to_csv('data/sofascore_momentum.csv', index=False, encoding='utf-8')
    else:
        momentum_df = pd.DataFrame()
        print("No momentum data was collected.")

    return momentum_df


def get_statistics_from_teams(teams, league_id, season_id, delay=5):
    """
    Fetches statistics data for a list of teams from the Sofascore API.

    Args:
        teams (list of dict): List of team dictionaries with 'id' key for team IDs.
        league_id (str): The league identifier for the statistics.
        season_id (str): The season identifier for the statistics.
        delay (int): Delay in seconds between API requests to avoid rate limiting.
        save_path (str): Path to save the resulting DataFrame as a CSV file.

    Returns:
        DataFrame: Combined statistics data for all teams, or empty DataFrame if none collected.
    """
    
    dfs = []

    for team in teams:
        time.sleep(delay)
        team_id = team['id']
        
        # Get statistics for the current team
        try:
            statistics = get_team_statistics(team_id, league_id, season_id)
            dfs.append(statistics)
        except:
            continue
        
    # Concatenate all dataframes and save to CSV
    if dfs:
        os.makedirs('data', exist_ok=True)
        statistics_df = pd.concat(dfs, ignore_index=True)
        statistics_df.to_csv('data/sofascore_teams_statistics.csv', index=False, encoding='utf-8')
    else:
        statistics_df = pd.DataFrame()
        print("No statistics data was collected.")

    return statistics_df


def get_statistics_from_team_ids(teams, league_id, season_id, delay=5):
    """
    Fetches statistics data for a list of teams from the Sofascore API.

    Args:
        teams (list of dict): List of team dictionaries with 'id' key for team IDs.
        league_id (str): The league identifier for the statistics.
        season_id (str): The season identifier for the statistics.
        delay (int): Delay in seconds between API requests to avoid rate limiting.
        save_path (str): Path to save the resulting DataFrame as a CSV file.

    Returns:
        DataFrame: Combined statistics data for all teams, or empty DataFrame if none collected.
    """
    
    dfs = []

    for team in teams:
        time.sleep(delay)
        team_id = team
        
        # Get statistics for the current team
        try:
            statistics = get_team_statistics(team_id, league_id, season_id)
            dfs.append(statistics)
        except:
            continue
        
    # Concatenate all dataframes and save to CSV
    if dfs:
        os.makedirs('data', exist_ok=True)
        statistics_df = pd.concat(dfs, ignore_index=True)
        statistics_df.to_csv('data/sofascore_teams_statistics.csv', index=False, encoding='utf-8')
    else:
        statistics_df = pd.DataFrame()
        print("No statistics data was collected.")

    return statistics_df


def get_highlights_from_events(events, delay=5):
    """
    Fetches highlight data for a list of events from the Sofascore API.

    Args:
        events (list of dict): List of events.

    Returns:
        DataFrame: Combined highlight data for all events, or an empty DataFrame if none collected.
    """
    
    dfs = []

    for event in events:
        time.sleep(delay)  # Wait for the specified delay before making the next request
        event_id = event
        
        # Get highlight for the current event
        try:
            highlight = get_highlights(event_id)  # Call the function to get highlight
            dfs.append(highlight)  # Append the highlight DataFrame to the list
        except Exception as e:
            print(f"Error retrieving highlight for event {event_id}: {e}")
            continue  # Continue to the next event if there's an error
        
    # Concatenate all dataframes and save to CSV
    if dfs:
        os.makedirs('data', exist_ok=True)  # Create the directory if it doesn't exist
        highlight_df = pd.concat(dfs, ignore_index=True)  # Concatenate all DataFrames
        highlight_df.to_csv('data/sofascore_highlight.csv', index=False, encoding='utf-8')  # Save to CSV
    else:
        highlight_df = pd.DataFrame()  # Return an empty DataFrame if no data was collected
        print("No highlight data was collected.")

    return highlight_df


def get_groups_from_league(league_id, season_id):
    """
    Fetches and saves standings for each group in a specified league and season as separate CSV files.
    
    Args:
        league_id (str): Unique identifier for the league.
        season_id (str): Unique identifier for the season.

    Returns:
        DataFrame: Combined DataFrame of the last processed group standings.
    """

    # API endpoint for league standings
    api_url = f'https://www.sofascore.com/api/v1/unique-tournament/{league_id}/season/{season_id}/standings/total'
    
    # Fetch data from API
    data = request_to_json(api_url)
    column_names = ['Equipo', 'Pos', 'PJ', 'PG', 'GA', 'GC', 'PP', 'PE', 'Pts', 'Dif', 'team_id', 'Escudo']
    dfs = []

    # Process each group in standings
    for i in range(len(data['standings'])):
        group_df = pd.DataFrame(data['standings'][i]['rows'])
        
        # Extract team ID and logo URL
        group_df['team_id'] = group_df['team'].apply(lambda x: x['id'] if isinstance(x, dict) else None)
        group_df['Escudo'] = group_df['team_id'].apply(lambda x: f'https://api.sofascore.app/api/v1/team/{x}/image' if x else None)
        group_df['team'] = group_df['team'].apply(lambda x: x['name'] if isinstance(x, dict) else None)
        
        # Drop unnecessary columns and rename
        group_df = group_df.drop(columns=['descriptions', 'promotion', 'id'])
        group_df.columns = column_names
        
        # Save group data to CSV
        letter = chr(65 + i)
        group_df.to_csv(f'data/sofascore_group_{letter}.csv', index=False, encoding='utf-8')
        dfs.append(group_df)

    return dfs


def get_shotmap_from_events(events, delay=5):
    """
    Fetches and combines shotmap data for a list of events, with an optional delay between requests.

    Args:
        events (list): List of event IDs to fetch shotmap data for.
        delay (int, optional): Time in seconds to wait between API requests. Defaults to 5.

    Returns:
        pd.DataFrame: Combined DataFrame of shotmap data for all events.
    """
    dfs = []

    for event in events:
        time.sleep(delay)
        event_id = event
        
        # Attempt to fetch shotmap for the current event
        try:
            shotmap = get_shotmap(event_id)
            dfs.append(shotmap)
        except Exception as e:
            print(f"Error retrieving shotmap for event {event_id}: {e}")
            continue
        
    # Concatenate and save all DataFrames if data was collected
    if dfs:
        os.makedirs('data', exist_ok=True)
        shotmap_df = pd.concat(dfs, ignore_index=True)
        shotmap_df.to_csv('data/sofascore_shotmap.csv', index=False, encoding='utf-8')
    else:
        shotmap_df = pd.DataFrame()
        print("No shotmap data was collected.")

    return shotmap_df


def get_profile_from_players(players, delay=5):
    """
    Collects profiles of multiple players and saves the data to a CSV file.

    Args:
        players (list): A list of dictionaries, each containing a 'link' key with the player's URL.

    Returns:
        DataFrame: A pandas DataFrame containing the collected player profiles.
    """
    dfs = []

    for player in players:
        time.sleep(delay)
        player_url = player['link']
        player_data = get_player_profile(player_url)
        dfs.append(player_data)

    if dfs:
        # Create a directory to store the data
        os.makedirs('data', exist_ok=True)

        # Convert the data into a DataFrame and save it as a CSV file
        player_profile_df = pd.DataFrame(dfs)
        player_profile_df.to_csv('data/sofascore_player_profile.csv', index=False, encoding='utf-8')
    else:
        player_profile_df = pd.DataFrame()
        print("No player profile was collected.")

    return player_profile_df


def get_incidents_from_events(events, delay=5):
    """
    Fetches incident data for a list of events from the Sofascore API.

    Args:
        events (list of dict): List of events.

    Returns:
        DataFrame: Combined incident data for all events, or an empty DataFrame if none collected.
    """
    
    dfs = []

    for event in events:
        time.sleep(delay)  # Wait for the specified delay before making the next request
        event_id = event
        
        # Get incidents for the current event
        try:
            incidents = get_incidents(event_id)  # Call the function to get incidents
            dfs.append(incidents)  # Append the incident DataFrame to the list
        except Exception as e:
            print(f"Error retrieving incidents for event {event_id}: {e}")
            continue  # Continue to the next event if there's an error
        
    # Concatenate all dataframes and save to CSV
    if dfs:
        os.makedirs('data', exist_ok=True)  # Create the directory if it doesn't exist
        incidents_df = pd.concat(dfs, ignore_index=True)  # Concatenate all DataFrames
        incidents_df.to_csv('data/sofascore_incidents.csv', index=False, encoding='utf-8')  # Save to CSV
    else:
        incidents_df = pd.DataFrame()  # Return an empty DataFrame if no data was collected
        print("No incident data was collected.")

    return incidents_df


def get_total_event_from_season(league_id, season_id, rounds, delay=5):
    """
    Fetches unique event details from a given league, season, and rounds.

    Args:
        league_id (str): Unique identifier for the league.
        season_id (str): Unique identifier for the season.
        rounds (list): List of round numbers to fetch events for.

    Returns:
        pandas.DataFrame: DataFrame containing event details for the specified rounds.
    """
    events = []

    # Iterate over rounds to fetch event details
    for round in range(rounds):
        round_number = round + 1
        time.sleep(delay)
        api_url = f'https://www.sofascore.com/api/v1/unique-tournament/{league_id}/season/{season_id}/events/round/{round_number}'
        data = request_to_json(api_url)

        # Extract event IDs and related details
        for event in range(len(data['events'])):
            event_id = data['events'][event]['id']
            home_id = data['events'][event]['homeTeam']['id']
            home_shortName = data['events'][event]['homeTeam']['shortName']
            home_score = data['events'][event].get('homeScore', {}).get('display', )
            away_id = data['events'][event]['awayTeam']['id']
            away_shortName = data['events'][event]['awayTeam']['shortName']
            away_score = data['events'][event].get('awayScore', {}).get('display', )

            event_dic = {
                'event_id': event_id,
                'round_number': round,
                'home_id': home_id,
                'home_shortName': home_shortName,
                'home_score': home_score,
                'away_id': away_id,
                'away_shortName': away_shortName,
                'away_score': away_score
            }

            events.append(event_dic)

    # Convert the events list to a pandas DataFrame
    events_df = pd.DataFrame(events)

    # Export to CSV
    os.makedirs('data', exist_ok=True)
    events_df.to_csv('data/sofascore_events_total.csv', index=False, encoding='utf-8')

    return events_df


# Support functions


def determine_position(order, def_count, mid_0_count, mid_1_count, mid_2_count, ata_count, substitute):
    """
    Determines the position, line, and latitude of a player based on their order in the lineup.

    Args:
        order (int): Player's order in the lineup.
        def_count (int): Number of defenders.
        mid_0_count (int): Number of midfielders in the first group.
        mid_1_count (int): Number of midfielders in the second group.
        mid_2_count (int): Number of midfielders in the third group.
        ata_count (int): Number of attackers.
        substitute (bool): Whether the player is a substitute.

    Returns:
        tuple: (line, latitude, position)
    """
    home_por = 1
    
    if order == home_por:
        line = 'por'
        lat = '1/1'
        pos = 'POR'
    elif order <= home_por + def_count:
        line = 'def'
        lat = f'{order - home_por}/{def_count}'
        pos = 'DEF'
    elif order <= home_por + def_count + mid_0_count:
        line = 'mid_0'
        lat = f'{order - home_por - def_count}/{mid_0_count}'
        pos = 'MED'
    elif order <= home_por + def_count + mid_0_count + mid_1_count:
        line = 'mid_1'
        lat = f'{order - home_por - def_count - mid_0_count}/{mid_1_count}'
        pos = 'MED'
    elif order <= home_por + def_count + mid_0_count + mid_1_count + mid_2_count:
        line = 'mid_2'
        lat = f'{order - home_por - def_count - mid_0_count - mid_1_count}/{mid_2_count}'
        pos = 'MED'
    elif order <= home_por + def_count + mid_0_count + mid_1_count + mid_2_count + ata_count:
        line = 'ata'
        lat = f'{order - home_por - def_count - mid_0_count - mid_1_count - mid_2_count}/{ata_count}'
        pos = 'ATA'
    elif order > 11 and substitute:
        line = None
        lat = None
        pos = 'SUS'
    elif order > 11 and not substitute:
        line = None
        lat = None
        pos = 'RES'
    else:
        line = None
        lat = None
        pos = None

    return line, lat, pos


def create_team_df(players, formation, def_count, mid_0_count, mid_1_count, mid_2_count, ata_count, team_name, is_home):
    """
    Creates a DataFrame for a team based on players' data and formation.

    Args:
        players (list): List of player dictionaries with their details.
        formation (str): Team formation in 'def-mid-ata' format.
        def_count (int): Number of defenders.
        mid_0_count (int): Number of midfielders in the first group.
        mid_1_count (int): Number of midfielders in the second group.
        mid_2_count (int): Number of midfielders in the third group.
        ata_count (int): Number of attackers.
        team_name (str): Name of the team.
        is_home (bool): Whether the team is the home team.

    Returns:
        pd.DataFrame: DataFrame containing player details and team information.
    """
    team_data = []
    for j, player in enumerate(players):
        name = player['player']['name']
        id = player['player']['id']
        jersey = player['shirtNumber']
        position = player.get('position', '')
        substitute = player['substitute']
        minutes = player.get('statistics', {}).get('minutesPlayed', 0)
        
        order = j + 1
        line, lat, pos = determine_position(order, def_count, mid_0_count, mid_1_count, mid_2_count, ata_count, substitute)

        team_data.append([name, id, jersey, position, substitute, minutes, order, line, lat, pos])

    df = pd.DataFrame(team_data, columns=['player', 'id', 'jersey', 'position', 'substitute', 'minutes', 'order', 'line', 'lat', 'pos'])
    df['team'] = team_name
    df['formation'] = formation
    df['defense'] = def_count
    df['midfield'] = mid_0_count + mid_1_count + mid_2_count
    df['attack'] = ata_count
    df['local'] = 'Home' if is_home else 'Away'
    
    return df


def get_lineups(event_id):
    """
    Retrieves the lineups for a given event from Sofascore.

    Parameters:
        event_id (int): The unique identifier for the event.

    Returns:
        dict: The JSON response containing lineup information.
    """
    api_url = f'https://www.sofascore.com/api/v1/event/{event_id}/lineups'
    data = request_to_json(api_url)
    return data


def get_average_positions(event_id):
    """
    Retrieves the average positions for players in a given event from Sofascore.

    Parameters:
        event_id (int): The unique identifier for the event.

    Returns:
        dict: The JSON response containing average position information.
    """
    api_url = f'https://www.sofascore.com/api/v1/event/{event_id}/average-positions'
    data = request_to_json(api_url)
    return data


def get_event_data(event_id):
    """
    Retrieves general data for a given event from Sofascore.

    Parameters:
        event_id (int): The unique identifier for the event.

    Returns:
        dict: The JSON response containing event data.
    """
    api_url = f'https://www.sofascore.com/api/v1/event/{event_id}'
    data = request_to_json(api_url)
    return data


def get_tournament_standing(tournament_id, season_id):
    """
    Fetches the standings of a specific tournament and season from Sofascore.

    Args:
        tournament_id (str): The unique identifier for the tournament.
        season_id (str): The unique identifier for the season.

    Returns:
        dict: A dictionary containing league, country, season, team names, and team IDs.
    """
    api_url = f'https://www.sofascore.com/api/v1/unique-tournament/{tournament_id}/season/{season_id}/standings/total'

    try:
        data = request_to_json(api_url)

        league = data['standings'][0]['tournament']['name']
        country = data['standings'][0]['tournament']['category']['name']
        season = datetime.fromtimestamp(data['standings'][0]['updatedAtTimestamp']).year

        teams_name = [row['team']['name'] for row in data['standings'][0]['rows']]
        teams_id = [row['team']['id'] for row in data['standings'][0]['rows']]

        return {
            'league': league,
            'country': country,
            'season': season,
            'teams_name': teams_name,
            'teams_id': teams_id
        }

    except requests.exceptions.RequestException as e:
        print(f'Error fetching tournament standings: {e}')
        return None
    

def get_player_tournaments(player_id):
    """
    Fetches the tournaments and seasons a player has participated in from the Sofascore API.

    Args:
        player_id (int): The unique identifier for the player in Sofascore.

    Returns:
        DataFrame: A pandas DataFrame containing tournament and season information for the player.
    """
    
    tournaments = []
    api_url = f'https://www.sofascore.com/api/v1/player/{player_id}/statistics/seasons'
    
    data = request_to_json(api_url)

    current_year = str(datetime.now().year)
    
    # Loop through each tournament and its seasons in the JSON data
    for tournament in data['uniqueTournamentSeasons']:
        for season in tournament['seasons']:
            season_year = int(season['year'][-2:])
            if season_year > int(current_year[-2:]) - 2:  # Only include seasons from the last two years
                competition_name = season['name']
                tournaments_id = tournament['uniqueTournament']['id']
                season_id = season['id']
                tournaments.append([competition_name, tournaments_id, season_id])

    # Convert the list of tournaments to a pandas DataFrame
    tournaments_df = pd.DataFrame(tournaments, columns=['competition_name', 'tournaments_id', 'season_id'])
    tournaments_df['player_id'] = player_id
    
    return tournaments_df


def get_heatmap(player_id, league_id, season_id):
    """
    Fetches heatmap data for a player from a specific league and season from the Sofascore API.

    Args:
        player_id (int): Player's unique identifier in Sofascore.
        league_id (int): League's unique identifier in Sofascore.
        season_id (int): Season's unique identifier in Sofascore.

    Returns:
        DataFrame: Contains heatmap data with coordinates (x, y) and count of actions.
    """
    
    heatmap = []
    api_url = f'https://www.sofascore.com/api/v1/player/{player_id}/unique-tournament/{league_id}/season/{season_id}/heatmap/overall'
    
    try:
        data = request_to_json(api_url)

        if 'points' in data:
            for point in data['points']:
                x = point.get('x', 0)
                y = point.get('y', 0)
                count = point.get('count', 0)
                heatmap.append([x, y, count])
        else:
            print(f"No heatmap data found for player {player_id} in league {league_id} and season {season_id}.")

    except:
        # Return an empty DataFrame with appropriate columns if an exception occurs
        return pd.DataFrame(columns=['x', 'y', 'count', 'player_id', 'league_id', 'season_id'])

    heatmap_df = pd.DataFrame(heatmap, columns=['x', 'y', 'count'])
    heatmap_df['player_id'] = player_id
    heatmap_df['league_id'] = league_id
    heatmap_df['season_id'] = season_id
    
    return heatmap_df


def request_to_json(api_url):
    """Fetch and decode JSON data from the SofaScore API.

    Args:
        api_url (str): The specific endpoint path for the request.

    Returns:
        dict: The parsed JSON data from the API if successful, None otherwise.
    """    
    time.sleep(5)

    try:
        connection = http.client.HTTPSConnection("api.sofascore.com")
        connection.request("GET", api_url)
        response = connection.getresponse()
        data = response.read()
        connection.close()

        # Decode and parse JSON
        data = data.decode('utf-8')
        return json.loads(data)

    except json.JSONDecodeError:
        print("Error: Unable to decode JSON response.")
        return None
    except Exception as e:
        print(f"Error fetching data: {e}")
        return None


def get_player_attributes(player_id):
    """
    Fetches and structures player attributes from Sofascore into a DataFrame.

    Args:
        player_id (int): The unique identifier for the player on Sofascore.

    Returns:
        pd.DataFrame: A DataFrame with columns for player position, attacking, technical, tactical, 
                      defending, and creativity attributes, as well as the player ID.
    """
    # API endpoint for player attribute overviews
    api_url = f'https://www.sofascore.com/api/v1/player/{player_id}/attribute-overviews'
    
    # Fetch the JSON data from the API
    data = request_to_json(api_url)

    # Extract key attributes
    attributes = {
        'Posición': data['averageAttributeOverviews'][0]['position'],
        'Ataque': data['averageAttributeOverviews'][0]['attacking'],
        'Técnica': data['averageAttributeOverviews'][0]['technical'],
        'Táctica': data['averageAttributeOverviews'][0]['tactical'],
        'Defensa': data['averageAttributeOverviews'][0]['defending'],
        'Creatividad': data['averageAttributeOverviews'][0]['creativity']
    }

    # Structure attributes into a DataFrame
    attributes_df = pd.DataFrame([attributes], columns=['Posición', 'Ataque', 'Técnica', 'Táctica', 'Defensa', 'Creatividad'])
    attributes_df['player_id'] = player_id
    
    return attributes_df


def get_player_statistics(player_id, league_id, season_id):
    """
    Fetches and organizes player statistics from Sofascore into a DataFrame.
    """
    api_url = f'https://www.sofascore.com/api/v1/player/{player_id}/unique-tournament/{league_id}/season/{season_id}/statistics/overall'
    
    try:
        data = request_to_json(api_url)
    except requests.exceptions.RequestException:
        print(f"No statistics data found for player {player_id} in league {league_id} and season {season_id}.")
        return pd.DataFrame()
    
    statistics = data['statistics']
    statistics_df = pd.DataFrame([statistics])
    
    # Diccionario de traducción
    translations = {
        'rating': 'Puntaje',
        'goals': 'Goles',
        'assists': 'Asistencias',
        'goalsAssistsSum': 'Goles + Asistencias',
        'accuratePasses': 'Pases precisos',
        'inaccuratePasses': 'Pases fallados',
        'totalPasses': 'Pases totales',
        'accuratePassesPercentage': 'Precisión de pase %',
        'accurateFinalThirdPasses': 'Pases precisos en tercio final',
        'keyPasses': 'Pases clave',
        'successfulDribbles': 'Regates completados',
        'successfulDribblesPercentage': 'Efectividad en regates %',
        'interceptions': 'Intercepciones',
        'yellowCards': 'Tarjetas amarillas',
        'directRedCards': 'Rojas directas',
        'redCards': 'Tarjetas rojas',
        'accurateCrosses': 'Centros precisos',
        'accurateCrossesPercentage': 'Precisión de centros %',
        'totalShots': 'Remates',
        'shotsOnTarget': 'Remates al arco',
        'shotsOffTarget': 'Remates fuera',
        'aerialDuelsWon': 'Duelos aéreos ganados',
        'aerialDuelsWonPercentage': 'Efectividad en duelos aéreos %',
        'totalDuelsWon': 'Duelos ganados',
        'totalDuelsWonPercentage': 'Efectividad en duelos %',
        'minutesPlayed': 'Minutos jugados',
        'goalConversionPercentage': 'Goles convertidos %',
        'penaltiesTaken': 'Penales ejecutados',
        'penaltyGoals': 'Penales convertidos',
        'shotFromSetPiece': 'Remates de pelota parada',
        'accurateLongBalls': 'Pases largos precisos',
        'accurateLongBallsPercentage': 'Precisión de pase largo %',
        'clearances': 'Despejes',
        'errorLeadToShot': 'Errores seguidos por remate',
        'wasFouled': 'Faltas recibidas',
        'fouls': 'Faltas cometidas',
        'ownGoals': 'Autogoles',
        'dribbledPast': 'Regateado',
        'offsides': 'Fueras de juego',
        'blockedShots': 'Remates bloqueados',
        'passToAssist': 'Pases al asistidor',
        'saves': 'Atajadas',
        'crossesNotClaimed': 'Centros perdidos',
        'matchesStarted': 'Partidos de titular',
        'totalCross': 'Centros totales',
        'duelLost': 'Duelos perdidos',
        'aerialLost': 'Pérdidas aéreas',
        'attemptPenaltyMiss': 'Penales errados',
        'totalLongBalls': 'Pases largos totales',
        'yellowRedCards': 'Doble amarilla',
        'substitutionsIn': 'Sustituciones ingresando',
        'substitutionsOut': 'Sustituciones saliendo',
        'goalKicks': 'Saques de arco',
        'ballRecovery': 'Recuperaciones',
        'id': 'stats_id',
        'type': 'type',
        'appearances': 'Partidos jugados'
    }
    
    # Traducir las columnas que coincidan
    statistics_df.rename(columns=translations, inplace=True)
    
    # Agregar identificadores
    statistics_df['player_id'] = player_id
    statistics_df['league_id'] = league_id
    statistics_df['season_id'] = season_id

    return statistics_df


def get_highlights(event_id):
    """
    Retrieves general data for a given event from Sofascore.

    Parameters:
        event_id (int): The unique identifier for the event.

    Returns:
        dict: The JSON response containing highlights data.
    """
    api_url = f'https://www.sofascore.com/api/v1/event/{event_id}/highlights'
    data = request_to_json(api_url)

    event_id = int(event_id)
    title = data['highlights'][0]['title']
    video = data['highlights'][0]['url']
    thumbnail = data['highlights'][0]['thumbnailUrl']

    
    highlight = {
        'event_id': [event_id],
        'title': [title],
        'video': [video],
        'thumbnail': [thumbnail]
    }

    highlights_df = pd.DataFrame(highlight)

    return highlights_df


def get_event_statistics(event_id):
    """
    Retrieves general data for a given event from Sofascore.

    Parameters:
        event_id (int): The unique identifier for the event.

    Returns:
        pd.DataFrame: A DataFrame containing statistics data with translated names.
    """
    api_url = f'https://www.sofascore.com/api/v1/event/{event_id}/statistics'
    
    # Make a request to the API and get the data
    data = request_to_json(api_url)

    event_id = int(event_id)
    match_overview = data['statistics'][0]['groups'][0]['statisticsItems']
    shots = data['statistics'][0]['groups'][1]['statisticsItems']
    attack = data['statistics'][0]['groups'][2]['statisticsItems']
    passes = data['statistics'][0]['groups'][3]['statisticsItems']
    duels = data['statistics'][0]['groups'][4]['statisticsItems']
    defending = data['statistics'][0]['groups'][5]['statisticsItems']
    goalkeeping = data['statistics'][0]['groups'][6]['statisticsItems']

    # Create DataFrames for each group of statistics
    df_match_overview = pd.DataFrame(match_overview)
    df_match_overview['Categoría'] = 'General'

    df_shots = pd.DataFrame(shots)
    df_shots['Categoría'] = 'Remates'

    df_attack = pd.DataFrame(attack)
    df_attack['Categoría'] = 'Ataques'

    df_passes = pd.DataFrame(passes)
    df_passes['Categoría'] = 'Pases'

    df_duels = pd.DataFrame(duels)
    df_duels['Categoría'] = 'Duelos'

    df_defending = pd.DataFrame(defending)
    df_defending['Categoría'] = 'Defensa'

    df_goalkeeping = pd.DataFrame(goalkeeping)
    df_goalkeeping['Categoría'] = 'Arquero'

    # Concatenate all DataFrames
    statistics_df = pd.concat([df_match_overview, df_shots, df_attack, df_passes, df_duels, df_defending, df_goalkeeping], ignore_index=True)
    statistics_df['event_id'] = event_id

    # Dictionary of translations
    translations = {
        "Ball possession": "Posesión",
        "Expected goals": "Goles esperados",
        "Total shots": "Remates totales",
        "Goalkeeper saves": "Atajadas",
        "Corner kicks": "Córners",
        "Fouls": "Faltas",
        "Passes": "Pases",
        "Tackles": "Entradas",
        "Free kicks": "Tiros libre",
        "Yellow cards": "Tarjetas amarillas",
        "Red cards": "Tarjetas rojas",
        "Shots on target": "Remates al arco",
        "Hit woodwork": "Palo",
        "Shots off target": "Remates fuera",
        "Blocked shots": "Remates bloqueados",
        "Shots inside box": "Remates dentro del área",
        "Shots outside box": "Remates fuera del área",
        "Through balls": "Pases en profundidad",
        "Touches in penalty area": "Toques en el área penal",
        "Offsides": "Fuera de juego",
        "Accurate passes": "Pases precisos",
        "Throw-ins": "Laterales",
        "Final third phase": "Fase de tercio final",
        "Long balls": "Pases largos",
        "Crosses": "Centros",
        "Duels": "Duelos",
        "Dispossessed": "Pérdidas de posesión",
        "Ground duels": "Duelos en el suelo",
        "Aerial duels": "Duelos aéreos",
        "Dribbles": "Regates",
        "Total tackles": "Entradas totales",
        "Interceptions": "Intercepciones",
        "Clearances": "Despejes",
        "Total saves": "Salvadas totales",
        "Goal kicks": "Saques de arco",
        "Errors lead to a shot": "Errores seguidos por remate",
        "High claims": "Centros descolgados"
    }

    # Apply translations to the 'name' column, keeping originals if there's no translation
    statistics_df['name'] = statistics_df['name'].map(translations).fillna(statistics_df['name'])

    # Drop unnecessary columns
    statistics_df = statistics_df.drop(columns=['compareCode', 'renderType'])

    return statistics_df


def get_momentum(event_id):
    """
    Fetches momentum data for a specified event from Sofascore's API.

    Args:
        event_id (int): Unique identifier for the event.

    Returns:
        pd.DataFrame: DataFrame containing momentum data points for the event.
    """
    api_url = f'https://www.sofascore.com/api/v1/event/{event_id}/graph'
    data = request_to_json(api_url)

    momentum_df = pd.DataFrame(data['graphPoints'])
    momentum_df['event_id'] = int(event_id)

    return momentum_df


def get_team_statistics(team_id, league_id, season_id):
    """
    Fetches and organizes team statistics from Sofascore into a DataFrame.

    Args:
        team_id (int): team's unique identifier in Sofascore.
        league_id (int): League's unique identifier in Sofascore.
        season_id (int): Season's unique identifier in Sofascore.

    Returns:
        pd.DataFrame: A DataFrame containing various team statistics, including scoring, passing, 
                      dribbling, defensive actions, and more. Each row is tagged with team, league, 
                      and season identifiers.
    """
    # API endpoint for team statistics overview
    api_url = f'https://www.sofascore.com/api/v1/team/{team_id}/unique-tournament/{league_id}/season/{season_id}/statistics/overall'
    
    try:
        # Fetch the JSON data from the API
        data = request_to_json(api_url)

    except requests.exceptions.RequestException:
        print(f'No statistics data found for team {team_id} in league {league_id} and season {season_id}.')
        return pd.DataFrame(columns=[
            'Goles convertidos', 'Goles recibidos', 'Asistencias', 'Remates', 'Goles de penal', 'Penales ejecutados',
            'Regates exitosos', 'Intentos de regate', 'Córners', 'Posesión promedio', 'Pases totales', 
            'Pases precisos', 'Precisión de pase %', 'Pases largos totales', 'Pases largos precisos', 
            'Precisión de pase largo %', 'Centros totales', 'Centros precisos', 'Precisión de centros %',
            'Vallas invictas', 'Intercepciones', 'Atajadas', 'Errores seguidos por remate', 'Duelos totales', 
            'Duelos ganados', 'Efectividad en duelos %', 'Duelos aéreos totales', 'Duelos aéreos ganados', 
            'Efectividad en duelos aéreos %', 'Fueras de juego', 'Faltas', 'Tarjetas amarillas', 
            'Doble amarilla', 'Tarjetas rojas', 'Remates en contra', 'Saques de arco', 'Recuperaciones', 
            'Tiros libre', 'ID', 'Partidos', 'Partidos otorgados', 'team_id', 'league_id', 'season_id'
        ])
    
    # Extract statistics data
    statistics = data['statistics']

    # Organize data into a DataFrame
    statistics_df = pd.DataFrame([statistics])
    
    column_names = [
        'Goles convertidos', 'Goles recibidos', 'Asistencias', 'Remates', 'Goles de penal', 'Penales ejecutados',
        'Regates exitosos', 'Intentos de regate', 'Córners', 'Posesión promedio', 'Pases totales', 
        'Pases precisos', 'Precisión de pase %', 'Pases largos totales', 'Pases largos precisos', 
        'Precisión de pase largo %', 'Centros totales', 'Centros precisos', 'Precisión de centros %',
        'Vallas invictas', 'Intercepciones', 'Atajadas', 'Errores seguidos por remate', 'Duelos totales', 
        'Duelos ganados', 'Efectividad en duelos %', 'Duelos aéreos totales', 'Duelos aéreos ganados', 
        'Efectividad en duelos aéreos %', 'Fueras de juego', 'Faltas', 'Tarjetas amarillas', 
        'Doble amarilla', 'Tarjetas rojas', 'Remates en contra', 'Saques de arco', 'Recuperaciones', 
        'Tiros libre', 'ID', 'Partidos', 'Partidos otorgados'
    ]

    statistics_df.columns = column_names

    # Add identifier columns
    statistics_df['team_id'] = team_id
    statistics_df['league_id'] = league_id
    statistics_df['season_id'] = season_id
    
    return statistics_df


def get_statistics_from_single_team(team_id, league_id, season_id):
    """
    Fetches and organizes team statistics from Sofascore into a DataFrame.

    Args:
        team_id (int): team's unique identifier in Sofascore.
        league_id (int): League's unique identifier in Sofascore.
        season_id (int): Season's unique identifier in Sofascore.

    Returns:
        pd.DataFrame: A DataFrame containing various team statistics, including scoring, passing, 
                      dribbling, defensive actions, and more. Each row is tagged with team, league, 
                      and season identifiers.
    """
    # API endpoint for team statistics overview
    api_url = f'https://www.sofascore.com/api/v1/team/{team_id}/unique-tournament/{league_id}/season/{season_id}/statistics/overall'
    
    try:
        # Fetch the JSON data from the API
        data = request_to_json(api_url)

    except requests.exceptions.RequestException:
        print(f'No statistics data found for team {team_id} in league {league_id} and season {season_id}.')
        return pd.DataFrame(columns=[
            'Goles convertidos', 'Goles recibidos', 'Asistencias', 'Remates', 'Goles de penal', 'Penales ejecutados',
            'Regates exitosos', 'Intentos de regate', 'Córners', 'Posesión promedio', 'Pases totales', 
            'Pases precisos', 'Precisión de pase %', 'Pases largos totales', 'Pases largos precisos', 
            'Precisión de pase largo %', 'Centros totales', 'Centros precisos', 'Precisión de centros %',
            'Vallas invictas', 'Intercepciones', 'Atajadas', 'Errores seguidos por remate', 'Duelos totales', 
            'Duelos ganados', 'Efectividad en duelos %', 'Duelos aéreos totales', 'Duelos aéreos ganados', 
            'Efectividad en duelos aéreos %', 'Fueras de juego', 'Faltas', 'Tarjetas amarillas', 
            'Doble amarilla', 'Tarjetas rojas', 'Remates en contra', 'Saques de arco', 'Recuperaciones', 
            'Tiros libre', 'ID', 'Partidos', 'Partidos otorgados', 'team_id', 'league_id', 'season_id'
        ])
    
    # Extract statistics data
    statistics = data['statistics']

    # Organize data into a DataFrame
    statistics_df = pd.DataFrame([statistics])
    
    column_names = [
        'Goles convertidos', 'Goles recibidos', 'Asistencias', 'Remates', 'Goles de penal', 'Penales ejecutados',
        'Regates exitosos', 'Intentos de regate', 'Córners', 'Posesión promedio', 'Pases totales', 
        'Pases precisos', 'Precisión de pase %', 'Pases largos totales', 'Pases largos precisos', 
        'Precisión de pase largo %', 'Centros totales', 'Centros precisos', 'Precisión de centros %',
        'Vallas invictas', 'Intercepciones', 'Atajadas', 'Errores seguidos por remate', 'Duelos totales', 
        'Duelos ganados', 'Efectividad en duelos %', 'Duelos aéreos totales', 'Duelos aéreos ganados', 
        'Efectividad en duelos aéreos %', 'Fueras de juego', 'Faltas', 'Tarjetas amarillas', 
        'Doble amarilla', 'Tarjetas rojas', 'Remates en contra', 'Saques de arco', 'Recuperaciones', 
        'Tiros libre', 'ID', 'Partidos', 'Partidos otorgados'
    ]

    statistics_df.columns = column_names

    # Add identifier columns
    statistics_df['team_id'] = team_id
    statistics_df['league_id'] = league_id
    statistics_df['season_id'] = season_id
    
    statistics_df.to_csv('data/sofascore_team_statistics.csv', index=False, encoding='utf-8')

    return statistics_df


def get_lineups_from_single_event(events, delay=5):
    """
    Processes a list of events to extract and organize lineup data and average player positions.

    Args:
        events (list): List of dictionaries containing event information.
        delay (int): Time to wait (in seconds) between requests to avoid overloading the server. Default is 5 seconds.

    Returns:
        pd.DataFrame: A DataFrame containing the lineup data and average player positions for all processed events.
    """
    dfs = []  # Initialize a list to store DataFrames for each event

    for event in events:
        time.sleep(delay)  # Wait before making the next request

        event_id = event
        
        try:
            data = get_event_data(event_id)
            status = data['event']['status']['type']

            if status == 'finished':
                # Get lineup, average positions, and event data
                lineups = get_lineups(event_id)
                average_positions = get_average_positions(event_id)

                # Extract and process formations for home and away teams
                home_formation = lineups['home']['formation']
                away_formation = lineups['away']['formation']

                # Process home formation
                home_groups_formation = home_formation.split('-')
                home_def = int(home_groups_formation[0])
                home_ata = int(home_groups_formation[-1])

                if len(home_groups_formation) == 4:
                    home_mid_0 = int(home_groups_formation[1])
                    home_mid_1 = 0
                    home_mid_2 = int(home_groups_formation[2])
                else:
                    home_mid_0 = 0
                    home_mid_1 = int(home_groups_formation[1])
                    home_mid_2 = 0

                # Process away formation
                away_groups_formation = away_formation.split('-')
                away_def = int(away_groups_formation[0])
                away_ata = int(away_groups_formation[-1])

                if len(away_groups_formation) == 4:
                    away_mid_0 = int(away_groups_formation[1])
                    away_mid_1 = 0
                    away_mid_2 = int(away_groups_formation[2])
                else:
                    away_mid_0 = 0
                    away_mid_1 = int(away_groups_formation[1])
                    away_mid_2 = 0

                # Initialize lists to store player data
                home = []
                away = []
                home_avg = []
                away_avg = []

                # Process home team players
                for j in range(len(lineups['home']['players'])):
                    player = lineups['home']['players'][j]
                    name = player['player']['name']
                    id = player['player']['id']
                    jersey = player['shirtNumber']
                    position = player.get('position', '')
                    substitute = player['substitute']
                    minutes = player.get('statistics', {}).get('minutesPlayed', 0)

                    if j < len(average_positions['home']):
                        avg_player = average_positions['home'][j]
                        avg_id = avg_player['player']['id']
                        averageX = avg_player['averageX']
                        averageY = avg_player['averageY']
                        pointsCount = avg_player['pointsCount']

                    order = j + 1
                    line, lat, pos = determine_position(order, home_def, home_mid_0, home_mid_1, home_mid_2, home_ata, substitute)
                    
                    # Append player data to home list
                    home.append([name, id, jersey, position, substitute, minutes, order, line, lat, pos])
                    home_avg.append([avg_id, averageX, averageY, pointsCount])

                # Process away team players
                for k in range(len(lineups['away']['players'])):
                    player = lineups['away']['players'][k]
                    name = player['player']['name']
                    id = player['player']['id']
                    jersey = player['shirtNumber']
                    position = player.get('position', '')
                    substitute = player['substitute']
                    minutes = player.get('statistics', {}).get('minutesPlayed', 0)

                    if k < len(average_positions['away']):
                        avg_player = average_positions['away'][k]
                        avg_id = avg_player['player']['id']
                        averageX = avg_player['averageX']
                        averageY = avg_player['averageY']
                        pointsCount = avg_player['pointsCount']

                    order = k + 1
                    line, lat, pos = determine_position(order, away_def, away_mid_0, away_mid_1, away_mid_2, away_ata, substitute)

                    # Append player data to away list
                    away.append([name, id, jersey, position, substitute, minutes, order, line, lat, pos])
                    away_avg.append([avg_id, averageX, averageY, pointsCount])

                # Create DataFrames for home and away teams
                home_df = pd.DataFrame(home, columns=['player', 'id', 'jersey', 'position', 'substitute', 'minutes', 'order', 'line', 'lat', 'pos'])
                home_df['local'] = 'Home'
                home_df['team'] = data['event']['homeTeam']['shortName']
                home_df['formation'] = home_formation
                home_df['defense'] = home_def
                home_df['midfield'] = home_mid_0 + home_mid_1 + home_mid_2
                home_df['attack'] = home_ata

                away_df = pd.DataFrame(away, columns=['player', 'id', 'jersey', 'position', 'substitute', 'minutes', 'order', 'line', 'lat', 'pos'])
                away_df['local'] = 'Away'
                away_df['team'] = data['event']['awayTeam']['shortName']
                away_df['formation'] = away_formation
                away_df['defense'] = away_def
                away_df['midfield'] = away_mid_0 + away_mid_1 + away_mid_2
                away_df['attack'] = away_ata

                # Create DataFrame for average player positions
                home_avg_position = pd.DataFrame(home_avg, columns=['avg_id', 'averageX', 'averageY', 'pointsCount'])
                away_avg_position = pd.DataFrame(away_avg, columns=['avg_id', 'averageX', 'averageY', 'pointsCount'])
                df_avg_position = pd.concat([home_avg_position, away_avg_position], ignore_index=True)
                df_avg_position.rename(columns={'avg_id': 'id'}, inplace=True)

                # Merge lineup data with average position data
                df = pd.concat([home_df, away_df], ignore_index=True)
                df_merged = pd.merge(df, df_avg_position, on='id', how='left')
                df_merged['event_id'] = event_id

                # Append the DataFrame to the list
                dfs.append(df_merged)

        except Exception as e:
            print(f"Error in processing lineup for event {event_id}: {e}")

    # Concatenate all DataFrames into one and save to CSV
    os.makedirs('data', exist_ok=True)
    lineups_df = pd.concat(dfs, ignore_index=True)
    lineups_df.to_csv('data/sofascore_lineup.csv', index=False, encoding='utf-8')

    return lineups_df


def get_results_from_single_event(events, delay=5):
    """
    Extracts match results from a list of events and returns a DataFrame.

    Args:
        events (list): A list of event dictionaries, each containing an 'id'.
        delay (int, optional): Delay in seconds between requests. Default is 5 seconds.

    Returns:
        pd.DataFrame: A DataFrame containing match results for each event.
    """
    # List to store DataFrames for each event
    dfs = []

    for event in events:
        # Respect the delay between requests to avoid overloading the server
        time.sleep(delay)

        # Extract the event ID from the event dictionary
        event_id = event

        # Fetch event data using the event ID
        event_data = get_event_data(event_id)
        status = event_data['event']['status']['type']

        if status == 'finished':
            # Extract necessary details from the event data
            homeTeam_name = event_data['event']['homeTeam']['shortName']
            homeTeam_id = event_data['event']['homeTeam']['id']
            homeScore = int(event_data['event']['homeScore']['display'])
            awayTeam_name = event_data['event']['awayTeam']['shortName']
            awayTeam_id = event_data['event']['awayTeam']['id']
            awayScore = int(event_data['event']['awayScore']['display'])

            # Create a dictionary for the home team
            home_dic = {
                'event_id': event_id,
                'team': homeTeam_name,
                'team_id': homeTeam_id,
                'score_for': homeScore,
                'score_against': awayScore,
                'win': homeScore > awayScore,
                'draw': homeScore == awayScore,
                'loose': homeScore < awayScore,
                'local': 'Home'
            }

            # Create a dictionary for the away team
            away_dic = {
                'event_id': event_id,
                'team': awayTeam_name,
                'team_id': awayTeam_id,
                'score_for': awayScore,
                'score_against': homeScore,
                'win': awayScore > homeScore,
                'draw': awayScore == homeScore,
                'loose': awayScore < homeScore,
                'local': 'Away'
            }

            # Convert the dictionaries into DataFrames
            home_df = pd.DataFrame([home_dic])
            away_df = pd.DataFrame([away_dic])

            # Concatenate the home and away DataFrames into a single DataFrame
            df = pd.concat([home_df, away_df], ignore_index=True)

            # Append the DataFrame to the list
            dfs.append(df)

    # Concatenate all the DataFrames into one final DataFrame
    results_df = pd.concat(dfs, ignore_index=True)

    # Export the final DataFrame to a CSV file
    os.makedirs('data', exist_ok=True)
    results_df.to_csv('data/sofascore_results.csv', index=False, encoding='utf-8')

    return results_df


def get_shotmap(event_id):
    """
    Fetches shotmap data for a specific event, transforming it into a DataFrame with relevant columns.
    
    Args:
        event_id (str): Unique identifier for the event.

    Returns:
        DataFrame: Processed shotmap data with player and shot coordinates, goal coordinates, and home/away team IDs.
    """
    
    # API endpoint for shotmap data
    api_url = f'https://www.sofascore.com/api/v1/event/{event_id}/shotmap'
    data = request_to_json(api_url)

    # API endpoint for event team details
    teams_api_url = f'https://www.sofascore.com/api/v1/event/{event_id}'
    teams_data = request_to_json(teams_api_url)

    # Get home and away team IDs
    home = teams_data['event']['homeTeam']['id']
    away = teams_data['event']['awayTeam']['id']

    # Create DataFrame from shotmap data
    shotmap_df = pd.DataFrame(data['shotmap'])
    shotmap_df['event_id'] = int(event_id)

    # Extract player ID and coordinates
    shotmap_df['player'] = shotmap_df['player'].apply(lambda x: x['id'] if isinstance(x, dict) else None)
    shotmap_df['x'] = shotmap_df['playerCoordinates'].apply(lambda x: x['x'] if isinstance(x, dict) else None)
    shotmap_df['y'] = shotmap_df['playerCoordinates'].apply(lambda x: x['y'] if isinstance(x, dict) else None)
    
    # Extract goal coordinates
    shotmap_df['x_goal'] = shotmap_df['draw'].apply(lambda x: x['goal']['x'] if isinstance(x, dict) else None)
    shotmap_df['y_goal'] = shotmap_df['draw'].apply(lambda x: x['goal']['y'] if isinstance(x, dict) else None)
    
    # Map team ID based on whether it's a home or away shot
    shotmap_df['team'] = shotmap_df['isHome'].apply(lambda x: home if x else away)
    shotmap_df['isHome'] = shotmap_df['isHome'].apply(lambda x: 'home' if x else 'away')

    return shotmap_df


def get_event_from_season(tournament_id, season_id):
    """
    Fetches unique event IDs from a given tournament and season.

    Args:
        tournament_id (str): Unique identifier for the tournament.
        season_id (str): Unique identifier for the season.

    Returns:
        list: Unique list of event IDs.
    """
    # API endpoint with tournament and season IDs
    api_url = f'https://www.sofascore.com/api/v1/tournament/{tournament_id}/season/{season_id}/team-events/total'
    data = request_to_json(api_url)

    # Extract event IDs from nested JSON structure
    events = []
    for team in data['teamEvents']:
        for event in data['teamEvents'][team]:
            event_id = event['id']
            events.append(event_id)

    # Remove duplicates
    events = list(set(events))

    return events


def get_player_profile(player_url):
    """
    Scrapes player profile data from the given Sofascore URL.

    Args:
        player_url (str): URL of the player's profile page.

    Returns:
        dict: A dictionary containing the player's profile data.
    """
    import requests
    from bs4 import BeautifulSoup
    import re

    # Mapping of positions to full names
    position_map = {
        'ST': 'Delantero',
        'LW': 'Extremo izquierdo',
        'RW': 'Extremo derecho',
        'AM': 'Mediocampista ofensivo',
        'ML': 'Mediocampista izquierdo',
        'MC': 'Mediocampista central',
        'MR': 'Mediocampista derecho',
        'DM': 'Defensa mediocampo',
        'DL': 'Defensor izquierdo',
        'DC': 'Defensor central',
        'DR': 'Defensor derecho',
        'GK': 'Portero',
    }

    # Perform the HTTP request
    response = requests.get(player_url)
    response.raise_for_status()  # Check if the request was successful

    # Parse the HTML
    soup = BeautifulSoup(response.text, 'html.parser')

    # Helper function to extract text from a selector
    def extract_text(selector, index=None):
        elements = soup.select(selector)
        if index is not None:
            return elements[index].text.strip() if len(elements) > index else None
        return elements[0].text.strip() if elements else None

    # Extract player ID from the URL
    player_id = re.search(r'/(\d+)$', player_url)
    player_id = player_id.group(1) if player_id else None

    # Extract positions based on <text> tags containing abbreviations
    positions_found = [
        element.text.strip()
        for element in soup.find_all('text')
        if element.text.strip() in position_map
    ]

    # Translate positions to full names
    translated_positions = [position_map[pos] for pos in positions_found]

    # Build the player profile dictionary
    player_profile = {
        'player_id': player_id,
        'team': extract_text('.leMLNz'),
        'nationality': extract_text('.doveCn span'),
        'birth_date': extract_text('.gzlBsj', 1),
        'age': extract_text('.beCNLk', 1),
        'height': extract_text('.beCNLk', 2),
        'preferred_foot': extract_text('.beCNLk', 3),
        'position': extract_text('.beCNLk', 4),
        'shirt_number': extract_text('.beCNLk', 5),
        'market_value': extract_text('.imGAlA'),
        'pos': positions_found,  # Abbreviations (e.g., ['MC', 'RW'])
        'positions': translated_positions,  # Full names (e.g., ['Mediocampista central', 'Extremo derecho'])
    }

    return player_profile


def get_incidents(event_id):
    """
    Fetches incidents data for a specified event from Sofascore's API.

    Args:
        event_id (int): Unique identifier for the event.

    Returns:
        pd.DataFrame: DataFrame containing incidents data points for the event.
    """
    # Construct the URL to fetch incidents data for the event
    api_url = f'https://www.sofascore.com/api/v1/event/{event_id}/incidents'
    
    # Make the request and get the response in JSON format
    data = request_to_json(api_url)

    # Convert the incidents data into a DataFrame
    df = pd.DataFrame(data['incidents'])
    
    # Create a new DataFrame to store the processed incidents
    incidents_df = pd.DataFrame()
    
    # Process the incidents information
    incidents_df['time'] = df['time']
    incidents_df['incidentType'] = df['incidentType']
    incidents_df['incidentClass'] = df['incidentClass']
    
    # Convert 'isHome' to 'home' or 'away'
    incidents_df['isHome'] = df['isHome'].apply(lambda x: 'home' if x else 'away')

    # Process player data for incidents
    incidents_df['player_id'] = df['player'].apply(lambda x: x.get('id') if isinstance(x, dict) else None)
    incidents_df['player_shortName'] = df['player'].apply(lambda x: x.get('shortName') if isinstance(x, dict) else None)
    incidents_df['player_jerseyNumber'] = df['player'].apply(lambda x: x.get('jerseyNumber') if isinstance(x, dict) else None)

    # Process playerIn data (players who entered the field)
    incidents_df['playerIn_id'] = df['playerIn'].apply(lambda x: x.get('id') if isinstance(x, dict) else None)
    incidents_df['playerIn_shortName'] = df['playerIn'].apply(lambda x: x.get('shortName') if isinstance(x, dict) else None)
    incidents_df['playerIn_jerseyNumber'] = df['playerIn'].apply(lambda x: x.get('jerseyNumber') if isinstance(x, dict) else None)

    # Process playerOut data (players who left the field)
    incidents_df['playerOut_id'] = df['playerOut'].apply(lambda x: x.get('id') if isinstance(x, dict) else None)
    incidents_df['playerOut_shortName'] = df['playerOut'].apply(lambda x: x.get('shortName') if isinstance(x, dict) else None)
    incidents_df['playerOut_jerseyNumber'] = df['playerOut'].apply(lambda x: x.get('jerseyNumber') if isinstance(x, dict) else None)

    # Return the processed incidents DataFrame
    return incidents_df
