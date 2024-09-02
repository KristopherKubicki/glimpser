# Glimpser Integration Guide

This guide provides instructions on how to integrate Glimpser with Blue Iris, Home Assistant, and Hubitat. These integrations allow you to leverage Glimpser's powerful image processing and analysis capabilities within your existing smart home or surveillance setup.

## Table of Contents

1. [General Integration Concepts](#general-integration-concepts)
2. [Blue Iris Integration](#blue-iris-integration)
3. [Home Assistant Integration](#home-assistant-integration)
4. [Hubitat Integration](#hubitat-integration)

## General Integration Concepts

Before diving into specific integrations, it's important to understand the general concepts that apply to all integrations:

1. **API Endpoints**: Glimpser provides several API endpoints that can be used for integration. These are defined in `app/routes.py`.

2. **Configuration**: Glimpser's configuration settings in `app/config.py` may need to be adjusted for optimal integration.

3. **Scheduling**: Glimpser's scheduling capabilities (`app/utils/scheduling.py`) can be used to synchronize with external systems.

4. **Authentication**: Ensure that you use proper authentication when making API calls to Glimpser.

## Blue Iris Integration

Blue Iris is a popular video surveillance software. Here's how to integrate it with Glimpser:

1. **Configure Blue Iris Cameras**:
   - In Blue Iris, set up your cameras as usual.
   - For each camera you want to integrate with Glimpser, note down its Short Name (e.g., CAM1, CAM2).

2. **Set Up Glimpser Templates**:
   - For each Blue Iris camera, create a corresponding template in Glimpser.
   - Use the Blue Iris camera's snapshot URL as the template's URL.
   - Example: `http://<blue_iris_ip>:<port>/image/<camera_short_name>`

3. **Configure Blue Iris Alerts**:
   - In Blue Iris, go to Camera Properties > Alerts.
   - Set up an alert that triggers on motion or other events you're interested in.
   - In the alert action, add a webhook that calls Glimpser's screenshot capture endpoint:
     ```
     http://<glimpser_ip>:<port>/take_screenshot/<template_name>
     ```

4. **Glimpser Analysis Results**:
   - Set up a scheduled task in Blue Iris that periodically checks Glimpser's API for analysis results.
   - You can use Glimpser's `/captions` endpoint to get the latest analysis.
   - Use Blue Iris's scripting capabilities to process this data and trigger actions based on Glimpser's analysis.

## Home Assistant Integration

Home Assistant is an open-source home automation platform. Here's how to integrate it with Glimpser:

1. **Install RESTful Integration**:
   - In Home Assistant, install the RESTful integration if not already present.

2. **Configure Glimpser as a RESTful Sensor**:
   - Add the following to your Home Assistant `configuration.yaml`:
     ```yaml
     sensor:
       - platform: rest
         resource: http://<glimpser_ip>:<port>/captions
         name: Glimpser Analysis
         value_template: '{{ value_json.latest_caption }}'
         scan_interval: 60
     ```

3. **Create Automation**:
   - Use Home Assistant's automation capabilities to trigger actions based on Glimpser's analysis.
   - Example automation in `automations.yaml`:
     ```yaml
     - alias: "Glimpser Motion Detected"
       trigger:
         platform: state
         entity_id: sensor.glimpser_analysis
       condition:
         condition: template
         value_template: '{{ "motion" in trigger.to_state.state }}'
       action:
         service: notify.pushbullet
         data:
           message: "Motion detected by Glimpser: {{ trigger.to_state.state }}"
     ```

4. **Integrate Camera Feeds**:
   - Use Home Assistant's camera integration to add your camera feeds.
   - In Glimpser, create templates for each camera using the Home Assistant camera snapshot URL.

## Hubitat Integration

Hubitat is a home automation hub. Here's how to integrate it with Glimpser:

1. **Create a Maker API**:
   - In Hubitat, install the Maker API app if not already present.
   - Create a new Maker API instance and note down the API URL and access token.

2. **Set Up Glimpser Webhook**:
   - In Glimpser, create a new route in `app/routes.py` to receive webhooks from Hubitat:
     ```python
     @app.route('/hubitat_webhook', methods=['POST'])
     def hubitat_webhook():
         data = request.json
         # Process the data and trigger appropriate Glimpser actions
         return jsonify({"status": "success"}), 200
     ```

3. **Configure Hubitat Rule Machine**:
   - In Hubitat, use Rule Machine to create rules that send webhooks to Glimpser.
   - Example: When motion is detected, send a webhook to Glimpser to trigger a screenshot:
     ```
     http://<glimpser_ip>:<port>/take_screenshot/<template_name>
     ```

4. **Glimpser to Hubitat Communication**:
   - Use Glimpser's scheduling capabilities to periodically send analysis results to Hubitat.
   - Add a new scheduled job in `app/utils/scheduling.py`:
     ```python
     def send_to_hubitat():
         # Get latest analysis from Glimpser
         # Send to Hubitat using the Maker API
         pass

     scheduler.add_job(
         id="send_to_hubitat",
         func=send_to_hubitat,
         trigger="interval",
         minutes=5
     )
     ```

## Conclusion

These integration guides provide a starting point for connecting Glimpser with Blue Iris, Home Assistant, and Hubitat. Depending on your specific use case and setup, you may need to adjust and expand upon these instructions. Remember to always use secure authentication methods and follow best practices for API usage and network security.