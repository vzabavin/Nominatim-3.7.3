@SQLITE
@APIDB
Feature: Simple Tests
    Simple tests for internal server errors and response format.

    Scenario Outline: Testing different parameters
        When sending search query "Vaduz"
          | param       | value   |
          | <parameter> | <value> |
        Then at least 1 result is returned
        When sending xml search query "Vaduz"
          | param       | value   |
          | <parameter> | <value> |
        Then at least 1 result is returned
        When sending json search query "Vaduz"
          | param       | value   |
          | <parameter> | <value> |
        Then at least 1 result is returned
        When sending jsonv2 search query "Vaduz"
          | param       | value   |
          | <parameter> | <value> |
        Then at least 1 result is returned
        When sending geojson search query "Vaduz"
          | param       | value   |
          | <parameter> | <value> |
        Then at least 1 result is returned
        When sending geocodejson search query "Vaduz"
          | param       | value   |
          | <parameter> | <value> |
        Then at least 1 result is returned

    Examples:
     | parameter        | value |
     | addressdetails   | 0 |
     | polygon_text     | 0 |
     | polygon_kml      | 0 |
     | polygon_geojson  | 0 |
     | polygon_svg      | 0 |
     | accept-language  | de,en |
     | countrycodes     | li |
     | bounded          | 1 |
     | bounded          | 0 |
     | exclude_place_ids| 385252,1234515 |
     | limit            | 1000 |
     | dedupe           | 1 |
     | dedupe           | 0 |
     | extratags        | 0 |
     | namedetails      | 0 |

    Scenario: Search with invalid output format
        When sending search query "Berlin"
          | format |
          | fd$# |
        Then a HTTP 400 is returned

    Scenario Outline: Simple Searches
        When sending search query "<query>"
        Then the result is valid json
        When sending xml search query "<query>"
        Then the result is valid xml
        When sending json search query "<query>"
        Then the result is valid json
        When sending jsonv2 search query "<query>"
        Then the result is valid json
        When sending geojson search query "<query>"
        Then the result is valid geojson

    Examples:
     | query |
     | New York, New York |
     | France |
     | 12, Main Street, Houston |
     | München |
     | 東京都 |
     | hotels in nantes |
     | xywxkrf |
     | gh; foo() |
     | %#$@*&l;der#$! |
     | 234 |
     | 47.4,8.3 |

    Scenario: Empty XML search
        When sending xml search query "xnznxvcx"
        Then result header contains
          | attr        | value |
          | querystring | xnznxvcx |
          | more_url    | .*q=xnznxvcx.*format=xml |

    Scenario: Empty XML search with special XML characters
        When sending xml search query "xfdghn&zxn"xvbyx<vxx>cssdex"
        Then result header contains
          | attr        | value |
          | querystring | xfdghn&zxn"xvbyx<vxx>cssdex |
          | more_url    | .*q=xfdghn%26zxn%22xvbyx%3Cvxx%3Ecssdex.*format=xml |

    Scenario: Empty XML search with viewbox
        When sending xml search query "xnznxvcx"
          | viewbox |
          | 12,33,77,45.13 |
        Then result header contains
          | attr        | value |
          | querystring | xnznxvcx |
          | viewbox     | 12,33,77,45.13 |

    Scenario: Empty XML search with viewboxlbrt
        When sending xml search query "xnznxvcx"
          | viewboxlbrt |
          | 12,34.13,77,45 |
        Then result header contains
          | attr        | value |
          | querystring | xnznxvcx |
          | viewbox     | 12,34.13,77,45 |

    Scenario: Empty XML search with viewboxlbrt and viewbox
        When sending xml search query "pub"
          | viewbox        | viewboxblrt |
          | 12,33,77,45.13 | 1,2,3,4 |
        Then result header contains
          | attr        | value |
          | querystring | pub |
          | viewbox     | 12,33,77,45.13 |

    Scenario: Empty XML search with exluded place ids
        When sending xml search query "jghrleoxsbwjer"
          | exclude_place_ids |
          | 123,76,342565 |
        Then result header contains
          | attr              | value |
          | exclude_place_ids | 123,76,342565 |

    Scenario: Empty XML search with bad exluded place ids
        When sending xml search query "jghrleoxsbwjer"
          | exclude_place_ids |
          | , |
        Then result header has not attributes exclude_place_ids

    Scenario Outline: Wrapping of legal jsonp search requests
        When sending json search query "Tokyo"
            | param        | value |
            |json_callback | <data> |
        Then result header contains
            | attr         | value |
            | json_func    | <result> |

    Examples:
     | data    | result |
     | foo     | foo |
     | FOO     | FOO |
     | __world | __world |

    Scenario Outline: Wrapping of illegal jsonp search requests
        When sending json search query "Tokyo"
            | param        | value |
            |json_callback | <data> |
        Then a json user error is returned

    Examples:
      | data |
      | 1asd |
      | bar(foo) |
      | XXX['bad'] |
      | foo; evil |

    Scenario: Ignore jsonp parameter for anything but json
        When sending json search query "Malibu"
          | json_callback |
          | 234 |
        Then a HTTP 400 is returned
        When sending xml search query "Malibu"
          | json_callback |
          | 234 |
        Then the result is valid xml

    Scenario Outline: Empty search
        When sending <format> search query "YHlERzzx"
        Then exactly 0 results are returned

    Examples:
        | format |
        | json |
        | jsonv2 |
        | geojson |
        | geocodejson |

    Scenario: Search for non-existing coordinates
        When sending json search query "-21.0,-33.0"
        Then exactly 0 results are returned

    Scenario: Country code selection is retained in more URL (#596)
        When sending xml search query "Vaduz"
          | countrycodes |
          | pl,1,,invalid,undefined,%3Cb%3E,bo,, |
        Then result header contains
          | attr     | value |
          | more_url | .*&countrycodes=pl%2Cbo&.* |

    Scenario Outline: Search debug output does not return errors
        When sending debug search query "<query>"
        Then a HTTP 200 is returned

    Examples:
        | query |
        | Liechtenstein |
        | Triesen |
        | Pfarrkirche |
        | Landstr 27 Steinort, Triesenberg, 9495 |
        | 9497 |
        | restaurant in triesen |
