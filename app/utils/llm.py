
import datetime
import requests
import time 
import re
import json

from config import CHATGPT_KEY

last_429_error_time = None

def summarize(prompt, history=None, tokens=4096):

        # 4096 kind of hte max

        global last_429_error_time
        # Check if a 429 error occurred in the last 30 minutes
        if last_429_error_time and (datetime.datetime.now() - last_429_error_time) < datetime.timedelta(minutes=15):
            #print("Request blocked due to a recent 429 error.")
            return None

        headers = {
            "Authorization": f"Bearer {CHATGPT_KEY}"
        }
        url = "https://api.openai.com/v1/chat/completions"

         
        # TODO: make this configurable by the database instead

        messages = [{"role": "system", "content": [{"type": "text",
            "text": "Below are caption logs from several media sources that are relevant to me, the listener.  Summarize the logs and history into a technical and concise transcript of 10 lines for a personalized news station. Write one line per segment separated by newlines. Each line should contain a logically grouped together set of succint insights, forecasts and alerts that you generate. Keep it brief, don't use colorful language. The audience is highly educated and well informed.  Write plain text for each line. Start the summarization with a greeting, the date, time, temperature, an overall summary including the most major events. Include specifics. Can you tell a bigger story rather than just a list of camera feed captions? Prioritize local contexts. What are the takeaways for the listener? Consider the historic transcripts, no need to repeat unless it's an alert. Include uncommon insights. Be precise, dense, brief and specific.  Don't write timestamps. The time is %s CT. All timestamps from the provided cameras are in UTC. Have a swell sense of humor but use it very sparingly. Close with a classy short goodbye and station identification." % (datetime.datetime.now())  # utc?
            

            }]}]
        messages.append({"role": "user", "content": [{"type": "text", "text": prompt}]})
        if history:
            messages.append({"role": "user", "content": [{"type": "text", "text": 'Also, please note the previous transcripts.  Try to build on the history if you can, without repeating the older content. \n: ' + history}]})

        # Construct the payload with the prompt and images
        payload = {
            "model": "gpt-4o-mini", # cheaper and faster
            "messages": messages,
            "max_tokens": tokens # might even be less
        }

        # Send the request to the API
        result = None
        response = None
        try:
            response = requests.post(url, headers=headers, json=payload)
            #print(">>", response.text)
            if response.status_code == 429:
                last_429_error_time = datetime.datetime.now()
                print("429 error encountered. Blocking requests for 30 minutes.")
                return None
            result = response.json()
        except Exception as e:
            print(" warning! response issue", e)

        # Process the response
        # For demonstration, we'll just return the text response
        try:
            response_text = result['choices'][0]['message']['content'].replace('\n\n','\t').strip()
            ltokens = result['usage']['total_tokens']
            #print(">>", result['usage'])
            # TODO: logging.. 
            print(" total tokens $%0.5f" % ( ltokens * 0.01 / 1000))

            # TODO: actually, convert this to something else... 
            ljson = {}
            # TODO: 
            start_time = int(time.time())
            for line in re.findall(r'(.+?)(?:[\t\n]|$)', response_text, flags=re.DOTALL):
                line = line.replace('**','')
                line = re.sub('^\s?[\*\-]\s?', '', line, flags=re.DOTALL)
                line = line.strip()
                if len(line) > 1:
                    ljson[start_time] = line
                    start_time += 5

            print(">>>", ljson)
            # TODO: store the result , we paid for it
            return json.dumps(ljson)
        except Exception as e:
            print(" gpt exception", e, response)
            #if response is not None:
            #    print(" gpt exception text:", response.text)
            pass



