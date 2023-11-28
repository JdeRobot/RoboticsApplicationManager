visualization = {
    "none": [],
    "console": [{"module": "console",
                 "display": ":1",
                 "external_port": 1108,
                 "internal_port": 5901}],
    "gazebo_gra": [{
        "type": "module",
        "module": "console",
        "display": ":1",
        "external_port": 1108,
        "internal_port": 5901},
        {
        "type": "module",
        "width": 1024,
        "height": 768,
        "module": "gazebo_view",
        "display": ":2",
        "external_port": 6080,
        "internal_port": 5900
    },
        {
        "type": "module",
        "width": 1024,
        "height": 768,
        "module": "robot_display_view",
        "display": ":3",
        "external_port": 2303,
        "internal_port": 5902
    }
    ],
    "gazebo_rae": [{"type": "module",
                            "module": "console",
                            "display": ":1",
                            "external_port": 1108,
                            "internal_port": 5901},
                   {
        "type": "module",
        "width": 1024,
        "height": 768,
        "module": "gazebo_view",
        "display": ":2",
        "external_port": 6080,
        "internal_port": 5900
    }],
    "physic_gra": [{"module": "console",
                    "display": ":1",
                    "external_port": 1108,
                    "internal_port": 5901},
                   {
        "type": "module",
                "width": 1024,
        "height": 768,
        "module": "robot_display_view",
        "display": ":2",
        "external_port": 2303,
        "internal_port": 5902
    }],
    "physic_rae": [{"module": "console",
                    "display": ":1",
                    "external_port": 1108,
                    "internal_port": 5901},
                   {
        "type": "module",
        "width": 1024,
        "height": 768,
        "module": "robot_display_view",
        "display": ":2",
        "external_port": 2303,
        "internal_port": 5902
    }]
}
